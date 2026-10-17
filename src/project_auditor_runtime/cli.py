"""Interactive, learner-safe terminal front end for the controlled runtime."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
from pathlib import Path
import sys

from .backend import BackendError, create_backend
from .packaging import package_source
from .paths import resolve_specs
from .runner import ProjectAuditorRuntime
from .store import StoreError


class SessionError(RuntimeError):
    pass


def require_ok(result: dict) -> dict:
    if not result.get('ok'):
        raise SessionError(str(result.get('error_code', 'REQUEST_FAILED')))
    return result


def show_public(result: dict, write=print) -> None:
    """Render only DeliveryGate-approved text, never raw model/rubric objects."""
    public = result.get('learner_visible_payload') or {}
    for key in ('active_scope_notice', 'conceptual_nudge', 'concept_and_rationale_explanation'):
        if public.get(key):
            write(public[key])
    for key in ('initial_neutral_question', 'neutral_question', 'followup_question'):
        question = public.get(key)
        if isinstance(question, dict):
            write(question.get('neutral_question_prompt') or question.get('neutral_followup_prompt') or '')
    for approach in public.get('suggested_approaches', []):
        write(approach)


class InteractiveSession:
    def __init__(self, runtime, packet, *, read=input, write=print):
        self.runtime, self.packet = runtime, packet
        self.read, self.write = read, write
        self.request = copy.deepcopy(packet['request'])
        self.sid = self.request['defense_session_id']
        self.counter = 0
        self.date = datetime.now().strftime('%Y%m%d')

    def turn(self):
        self.counter += 1
        if self.counter > 9999:
            raise SessionError('Session turn limit reached.')
        return f'DTURN-{self.date}-{self.counter:04d}'

    def refresh(self):
        self.request['session_state_snapshot'] = self.runtime.store.get_doc_session_state(self.sid)
        self.request['as_of'] = datetime.now().astimezone().isoformat(timespec='seconds')
        self.request['task_id'] = f"CLI-{self.packet['token']}-{self.counter:04d}"
        return self.request

    def run(self):
        req = self.request
        desc = req['document_descriptor']
        self.runtime.store.initialize_doc_session(
            self.sid, project_id=req['project_id'], document_id=desc['document_id'],
            document_version=desc['document_version'], document_sha256=desc['document_sha256'],
            section_inventory=req['full_section_inventory'])
        self.write(f"Session {self.sid}; {len(self.packet['passages'])} sections. Source is never executed.")
        self.write('Answer normally; /hint, /idk (bilmiyorum), /quit. Help is recorded before display.')
        for offset in range(0, len(self.packet['passages']), 4):
            desc['batch_index'] = offset // 4 + 1
            req['operation'] = 'PREPARE_PROJECT_DEFENSE'
            req['prior_defense_batch_package'] = None
            req['defense_responses'] = []
            req['current_batch_passages'] = copy.deepcopy(self.packet['passages'][offset:offset + 4])
            active = {p['section_id'] for p in req['current_batch_passages']}
            state = self.runtime.store.get_doc_resume_manifest(self.sid)
            # Carry durable dimension statuses forward; never claim unexplored scope is inspected.
            for section in req['full_section_inventory']:
                section['in_current_batch'] = section['section_id'] in active
                section['prior_dimension_statuses'] = [
                    {'dimension': item['dimension'], 'status': item['status']}
                    for item in state['scope_items'] if item['section_id'] == section['section_id']]
            batch = f"DBATCH-{self.packet['token']}-{offset // 4 + 1}"
            turn = self.turn()
            result = require_ok(self.runtime.run(self.refresh(), exam_id=batch, attempt_id=turn, deliver=True))
            if not result.get('learner_visible_payload'):
                raise SessionError('No question prepared: ' + str(result.get('terminal_status')))
            show_public(result, self.write)
            public = result['learner_visible_payload']['initial_neutral_question']
            current_id = public['question_id']
            main_id = current_id
            while True:
                answer = self.read('You > ').strip()
                if answer == '/quit':
                    self.runtime.store.pause_doc_session(self.sid, turn_id=self.turn())
                    self.write('Paused. Responses and assistance history remain in the local state directory.')
                    return
                if not answer:
                    continue
                questions = self.runtime.store.get_doc_batch_questions(batch)
                q = next(q for q in questions if q['question_id'] == current_id)
                if answer in ('/hint', 'ipucu'):
                    disclosed = self.runtime.store.get_doc_session_state(self.sid)['disclosed_hint_ids']
                    hint = next((h for h in q.get('on_demand_hints', []) if h['hint_id'] not in disclosed), None)
                    if hint is None:
                        self.write('No further hint is available for this question.')
                    else:
                        delivery = self.runtime.delivery.deliver_doc_hint(
                            self.refresh(), batch_exam_id=batch, turn_id=self.turn(),
                            question_id=current_id, hint_id=hint['hint_id'])
                        if delivery['ok']:
                            show_public(delivery, self.write)
                        else:
                            self.write('Hint blocked: ' + delivery['error_code'])
                    continue
                if len(answer) > 8192:
                    self.write('Please keep your answer within 8192 characters.')
                    continue
                idk = answer.casefold() in ('/idk', 'bilmiyorum', "i don't know", 'idk')
                turn = self.turn()
                response_id = f"DRESP-{self.packet['token']}-{self.counter:04d}"
                self.runtime.store.record_doc_response(
                    self.sid, batch_exam_id=batch, response_id=response_id, turn_id=turn,
                    question_id=current_id, response_text=answer, is_idk_declaration=idk)
                response = {k: q[k] for k in ('question_id', 'section_id', 'passage_id', 'target_dimension')}
                response.update(response_id=response_id, turn_id=turn,
                                parent_question_id=q.get('_parent_question_id'), raw_response_text=answer,
                                is_idk_declaration=idk, declared_design_change=False,
                                external_verification_outcome=None,
                                criterion_ids_to_evaluate=[c['criterion_id'] for c in q['expected_explanation_criteria']])
                req['operation'] = 'ANALYZE_PROJECT_DEFENSE'
                req['prior_defense_batch_package'] = self.runtime.delivered_doc_batch(batch)
                req['defense_responses'] = [response]
                result = require_ok(self.runtime.run(self.refresh(), exam_id=batch, attempt_id=self.turn(), deliver=True))
                observations = result['engine_output']['orchestrator_only_payload']['defense_response_observations']
                obs = next((o for o in observations if o['response_id'] == response_id), None)
                if obs is None:
                    raise SessionError('No response evaluation delivered: ' + str(result.get('terminal_status')))
                # Only the verdict label is public; private criterion text never reaches the terminal.
                self.write('Response: ' + obs['evaluation_verdict'])
                teaching = obs.get('teaching_transition_packet')
                if teaching:
                    taught = require_ok(self.runtime.delivery.deliver_doc_teaching(
                        self.refresh(), batch_exam_id=batch, turn_id=self.turn(), question_id=current_id,
                        response_id=response_id, teaching_packet=teaching))
                    show_public(taught, self.write)
                followup = (result.get('learner_visible_payload') or {}).get('followup_question')
                if followup:
                    show_public(result, self.write)
                    current_id = followup['followup_question_id']
                    continue
                next_result = self.runtime.delivery.deliver_doc_next(
                    self.refresh(), batch_exam_id=batch, turn_id=self.turn(), after_question_id=main_id)
                if next_result.get('error_code') == 'NO_NEXT_QUESTION':
                    break
                require_ok(next_result)
                show_public(next_result, self.write)
                current_id = next_result['learner_visible_payload']['neutral_question']['question_id']
                main_id = current_id
        self.runtime.store.stop_doc_session(self.sid, turn_id=self.turn())
        self.write('Session finished. No independent competency or overall score is granted.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Socratic defense of a code file or UTF-8 project document.')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--file', type=Path, help='Code file (read, never executed)')
    source.add_argument('--doc', type=Path, help='Markdown or UTF-8 text document')
    parser.add_argument('--provider', choices=['ollama', 'gemini', 'openai', 'openrouter', 'codex'], default='ollama')
    parser.add_argument('--model', help='Provider model ID; defaults to qwen2.5:7b for Ollama, gpt-6.1-sol for Codex')
    parser.add_argument('--domain', help='Override the contract learning domain')
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--state-dir', type=Path, default=Path.home() / '.socratic-project-auditor')
    parser.add_argument('--dry-run', action='store_true', help='Print the generated packet; no model or state writes')
    args = parser.parse_args(argv)
    try:
        packet = package_source(args.file or args.doc, code=args.file is not None, domain=args.domain)
        if args.dry_run:
            print(json.dumps(packet, ensure_ascii=False, indent=2))
            return 0
        model = args.model or ('qwen2.5:7b' if args.provider == 'ollama' else None)
        specs = resolve_specs(Path(__file__).resolve().parents[2])
        backend = create_backend(specs, provider=args.provider, model=model, timeout=args.timeout)
        state = args.state_dir.expanduser().resolve()
        runtime = ProjectAuditorRuntime(specs.parent, state, backend=backend)
        session_dir = state / 'sessions'
        session_dir.mkdir(parents=True, exist_ok=True)
        manifest = session_dir / (packet['request']['defense_session_id'] + '.json')
        with manifest.open('x', encoding='utf-8') as stream:
            json.dump(packet, stream, ensure_ascii=False, indent=2)
        print(f'Provider: {args.provider}; model: {backend.model}. State: {state}')
        if args.provider != 'ollama':
            print('The selected provider receives the source and responses; API calls may be billable.')
        InteractiveSession(runtime, packet).run()
        return 0
    except (EOFError, KeyboardInterrupt):
        print('\nInterrupted. Previously recorded state is preserved.', file=sys.stderr)
        return 130
    except (OSError, UnicodeError, ValueError, BackendError, StoreError, SessionError) as exc:
        print('Auditor: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
