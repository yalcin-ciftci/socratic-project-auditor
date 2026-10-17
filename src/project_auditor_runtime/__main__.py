import argparse
import json
from pathlib import Path
import sys

from .runner import ProjectAuditorRuntime
from .validation import strict_json
from .backend import create_backend
from .paths import resolve_specs


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description='Morks controlled Project Auditor runtime')
    parser.add_argument('action', choices=[
        'init-ledger', 'run', 'state', 'hint', 'next', 'record-response',
        'init-doc-session', 'doc-state', 'doc-next', 'doc-followup', 'doc-hint',
        'record-doc-response', 'doc-teach', 'void-doc-question',
        'pause-doc-session', 'resume-doc-session', 'stop-doc-session', 'update-doc-version',
    ])
    parser.add_argument('--vault', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--provider', choices=['codex', 'ollama', 'gemini', 'openai', 'openrouter'], default='codex')
    parser.add_argument('--model')
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--ledger-id', default='LEDGER-PROJECT-AUDITOR')
    parser.add_argument('--exam-id')
    parser.add_argument('--attempt-id')
    parser.add_argument('--question-id')
    parser.add_argument('--hint-id')
    parser.add_argument('--session-id')
    parser.add_argument('--project-id')
    parser.add_argument('--document-id')
    parser.add_argument('--document-version')
    parser.add_argument('--document-sha256')
    parser.add_argument('--response-id')
    parser.add_argument('--reason')
    parser.add_argument('--deliver', action='store_true')
    args = parser.parse_args(argv)
    state = args.state_dir or args.vault / '.codex/scripts/.state/project-auditor'
    try:
        backend = create_backend(resolve_specs(args.vault), provider=args.provider, model=args.model)
        runtime = ProjectAuditorRuntime(args.vault, state, backend=backend)
        if args.action == 'init-ledger':
            result = {'ok': True, 'disclosure_state': runtime.store.initialize_ledger(args.ledger_id)}
        elif args.action == 'state':
            # This command is PRIVATE orchestrator input preparation, not learner delivery.
            result = {'ok': True, 'disclosure_state': runtime.store.get_ledger(args.ledger_id),
                      'prior_exam_package': runtime.delivered_exam(args.exam_id) if args.exam_id else None}
        elif args.action == 'init-doc-session':
            inv = None
            req = {}
            if args.request:
                req = strict_json(args.request.read_text(encoding='utf-8-sig'))
                inv = req.get('full_section_inventory')
            doc_desc = req.get('document_descriptor') if isinstance(req.get('document_descriptor'), dict) else {}
            snap = runtime.store.initialize_doc_session(
                args.session_id or req.get('defense_session_id'),
                project_id=args.project_id or req.get('project_id'),
                document_id=args.document_id or doc_desc.get('document_id'),
                document_version=args.document_version or doc_desc.get('document_version'),
                document_sha256=args.document_sha256 or doc_desc.get('document_sha256'),
                section_inventory=inv,
            )
            result = {'ok': True, 'session_state_snapshot': snap}
        elif args.action == 'doc-state':
            result = {
                'ok': True,
                'session_state_snapshot': runtime.store.get_doc_session_state(args.session_id),
                'resume_manifest': runtime.store.get_doc_resume_manifest(args.session_id),
                'prior_defense_batch_package': runtime.delivered_doc_batch(args.exam_id) if args.exam_id else None,
            }
        elif args.action == 'pause-doc-session':
            result = {'ok': True, 'session_state_snapshot': runtime.store.pause_doc_session(args.session_id, turn_id=args.attempt_id or 'DTURN-20261017-90')}
        elif args.action == 'resume-doc-session':
            result = {'ok': True, 'resume_manifest': runtime.store.resume_doc_session(args.session_id, turn_id=args.attempt_id or 'DTURN-20261017-91')}
        elif args.action == 'stop-doc-session':
            result = {'ok': True, 'session_state_snapshot': runtime.store.stop_doc_session(args.session_id, turn_id=args.attempt_id or 'DTURN-20261017-92')}
        elif args.action == 'update-doc-version':
            updated_secs = None
            if args.request:
                req = strict_json(args.request.read_text(encoding='utf-8-sig'))
                updated_secs = req.get('updated_sections')
            result = {
                'ok': True,
                'session_state_snapshot': runtime.store.update_doc_version(
                    args.session_id,
                    new_version=args.document_version,
                    new_sha256=args.document_sha256,
                    updated_sections=updated_secs,
                    turn_id=args.attempt_id or 'DTURN-20261017-95',
                ),
            }
        elif args.action == 'void-doc-question':
            result = {
                'ok': True,
                'session_state_snapshot': runtime.store.void_doc_question(
                    args.session_id,
                    batch_exam_id=args.exam_id,
                    question_id=args.question_id,
                    reason=args.reason or 'Defective question voided by orchestrator.',
                    turn_id=args.attempt_id or 'DTURN-20261017-99',
                ),
            }
        else:
            if not args.exam_id or not args.attempt_id or not args.request:
                parser.error('exam-id, attempt-id and request are required')
            request_text = args.request.read_text(encoding='utf-8-sig')
            if args.action == 'run':
                result = runtime.public_result(runtime.run(request_text, exam_id=args.exam_id, attempt_id=args.attempt_id, deliver=args.deliver))
            elif args.action == 'hint':
                result = runtime.delivery.deliver_hint(strict_json(request_text), exam_id=args.exam_id, attempt_id=args.attempt_id,
                    question_id=args.question_id, hint_id=args.hint_id)
            elif args.action == 'next':
                result = runtime.delivery.deliver_next(strict_json(request_text), exam_id=args.exam_id, attempt_id=args.attempt_id,
                    after_question_id=args.question_id)
            elif args.action == 'record-response':
                runtime.store.record_response(args.exam_id, args.attempt_id, args.question_id, strict_json(request_text)['raw_response_text'])
                result = {'ok': True}
            elif args.action == 'doc-next':
                result = runtime.delivery.deliver_doc_next(
                    strict_json(request_text), batch_exam_id=args.exam_id,
                    turn_id=args.attempt_id, after_question_id=args.question_id)
            elif args.action == 'doc-followup':
                result = runtime.delivery.deliver_doc_followup(
                    strict_json(request_text), batch_exam_id=args.exam_id,
                    turn_id=args.attempt_id, followup_question_id=args.question_id)
            elif args.action == 'doc-hint':
                result = runtime.delivery.deliver_doc_hint(
                    strict_json(request_text), batch_exam_id=args.exam_id,
                    turn_id=args.attempt_id, question_id=args.question_id, hint_id=args.hint_id)
            elif args.action == 'record-doc-response':
                req = strict_json(request_text)
                snap = runtime.store.record_doc_response(
                    args.session_id or req.get('defense_session_id'),
                    batch_exam_id=args.exam_id,
                    response_id=args.response_id or req['response_id'],
                    turn_id=args.attempt_id,
                    question_id=args.question_id or req['question_id'],
                    response_text=req['raw_response_text'],
                    is_idk_declaration=bool(req.get('is_idk_declaration', False)),
                    declared_design_change=bool(req.get('declared_design_change', False)),
                )
                result = {'ok': True, 'session_state_snapshot': snap}
            elif args.action == 'doc-teach':
                req = strict_json(request_text)
                teach_pkt = req['teaching_transition_packet']
                q_id = args.question_id or teach_pkt['closed_question_id']
                r_id = args.response_id or teach_pkt['closed_response_id']
                result = runtime.delivery.deliver_doc_teaching(
                    req['payload'],
                    batch_exam_id=args.exam_id,
                    turn_id=args.attempt_id,
                    question_id=q_id,
                    response_id=r_id,
                    teaching_packet=teach_pkt,
                )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('ok') else 2
    except Exception as exc:
        print(json.dumps({'ok': False, 'error_code': getattr(exc, 'code', type(exc).__name__), 'learner_visible_payload': None}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
