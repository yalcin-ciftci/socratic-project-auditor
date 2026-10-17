"""Orchestrator entry point. Only validated output can reach controlled delivery."""
from __future__ import annotations

import copy
from pathlib import Path

from .backend import BackendError, CodexBackend
from .delivery import DeliveryGate
from .store import RuntimeStore, StoreError, package_digest, doc_package_digest
from .validation import RuntimeValidator, strict_json, is_doc_defense_payload
from .paths import resolve_specs


class ProjectAuditorRuntime:
    def __init__(self, vault: Path, state_dir: Path, backend=None, semantic_reviewer=None):
        self.vault = Path(vault).resolve()
        self.agent_dir = resolve_specs(self.vault)
        self.store = RuntimeStore(state_dir)
        self.backend = backend or CodexBackend(self.agent_dir)
        reviewer = semantic_reviewer or getattr(self.backend, 'review', None)
        self.validator = RuntimeValidator(self.agent_dir, semantic_reviewer=reviewer)
        self.delivery = DeliveryGate(self.store, semantic_reviewer=reviewer)

    def delivered_exam(self, exam_id: str) -> dict | None:
        """Trusted canonical view: do not disclose or evaluate undelivered questions."""
        package = self.store.get_exam(exam_id)
        if package is None:
            return None
        package['registered_questions'] = [q for q in package['registered_questions'] if q['delivered_to_learner']]
        if not package['registered_questions']:
            return None
        package['exam_package_sha256'] = package_digest(package)
        return package

    def delivered_doc_batch(self, batch_exam_id: str) -> dict | None:
        """Trusted canonical view for document defense: only delivered, non-voided, open questions."""
        package = self.store.get_doc_batch(batch_exam_id)
        if package is None:
            return None
        package['registered_questions'] = [
            q for q in package['registered_questions']
            if q['delivered_to_learner'] and not q['voided'] and not q['defense_record_closed']
        ]
        if not package['registered_questions']:
            return None
        package['batch_package_sha256'] = doc_package_digest(package)
        return package

    @staticmethod
    def _failure(stage, error_code, *, terminal_status=None, validation=None, model_calls=0):
        return {'ok': False, 'stage': stage, 'error_code': error_code,
                'terminal_status': terminal_status, 'learner_visible_payload': None,
                'validation': validation, 'model_calls': model_calls}

    def run(self, payload, *, exam_id: str, attempt_id: str, deliver: bool = False) -> dict:
        # These identifiers belong to the outer orchestrator, never the model.
        try:
            parsed = strict_json(payload)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            parsed = {}
        if is_doc_defense_payload(parsed):
            return self.run_doc_defense(payload, batch_exam_id=exam_id, turn_id=attempt_id, deliver=deliver)
        claim = parsed.get('disclosure_state', {})
        ledger = self.store.get_ledger(claim.get('ledger_source_id')) if isinstance(claim, dict) else None
        prior = parsed.get('prior_exam_package')
        registry = {}
        if isinstance(prior, dict):
            trusted = self.delivered_exam(prior.get('exam_id', ''))
            if trusted:
                registry[trusted['exam_id']] = trusted
        pre = self.validator.preflight(payload, exam_registry=registry, ledger=ledger)
        if not pre['ok']:
            return self._failure('PRE', pre['error_code'], terminal_status=pre['terminal_status'], validation=pre)
        p = pre['payload']
        related = self.store.get_related_disclosures(objective_id=p['objective_id'],
                    artifact_ids=[a['artifact_id'] for a in p['code_artifacts']],
                    snapshot_ids=[a['snapshot_id'] for a in p['code_artifacts']])
        if any(e['ledger_id'] != ledger['ledger_source_id'] for e in related):
            return self._failure('PRE', 'RELATED_DISCLOSURE_LEDGER_MISMATCH')
        calls = 0
        checked = None
        repair = None
        for _ in range(2):
            try:
                calls += 1
                if hasattr(self.backend, 'generate'):
                    generated = self.backend.generate(p, repair=repair)
                else:
                    generated = self.backend(p)
                # Generation/review can take time. Never validate against a stale
                # in-memory ledger or package after concurrent disclosure.
                ledger = self.store.get_ledger(p['disclosure_state']['ledger_source_id'])
                registry = {}
                if isinstance(p.get('prior_exam_package'), dict):
                    trusted = self.delivered_exam(p['prior_exam_package']['exam_id'])
                    if trusted:
                        registry[trusted['exam_id']] = trusted
                current = self.validator.preflight(p, exam_registry=registry, ledger=ledger)
                if not current['ok']:
                    return self._failure('POST', current['error_code'], validation=current, model_calls=calls)
                checked = self.validator.postflight(p, generated, exam_registry=registry, ledger=ledger)
            except BackendError as exc:
                return self._failure('MODEL', str(exc), model_calls=calls)
            if checked['ok']:
                break
            if checked.get('rule') != 'POST-01' or repair is not None:
                return self._failure('POST', checked['error_code'], validation=checked, model_calls=calls)
            repair = {'rule': 'POST-01', 'error_code': checked['error_code'],
                      'schema_errors': checked.get('schema_errors', []),
                      'instruction': 'One format repair only. Return the full raw JSON object.'}
        if not checked or not checked['ok']:
            return self._failure('POST', (checked or {}).get('error_code', 'INVALID_OUTPUT_SCHEMA'), validation=checked, model_calls=calls)
        # A semantic reviewer may itself have waited on a model call.
        final_ledger = self.store.get_ledger(p['disclosure_state']['ledger_source_id'])
        final_registry = {}
        if isinstance(p.get('prior_exam_package'), dict):
            trusted = self.delivered_exam(p['prior_exam_package']['exam_id'])
            if trusted:
                final_registry[trusted['exam_id']] = trusted
        current = self.validator.preflight(p, exam_registry=final_registry, ledger=final_ledger)
        if not current['ok']:
            return self._failure('POST', current['error_code'], validation=current, model_calls=calls)
        output = checked['output']
        qs = output['orchestrator_only_payload']['socratic_questions']
        if qs:
            registered = []
            for q in qs:
                ref = q['source_ref']
                registered.append({'question_id': q['question_id'], 'question_type': q['question_type'],
                    'artifact_id': ref['artifact_id'], 'snapshot_id': ref['snapshot_id'],
                    'start_line': ref['start_line'], 'end_line': ref['end_line'],
                    'delivered_to_learner': False, 'immutable_criteria': copy.deepcopy(q['expected_explanation_criteria'])})
            package = {'exam_id': exam_id, 'created_as_of': p['as_of'], 'objective_id': p['objective_id'],
                       'registered_questions': registered}
            package['exam_package_sha256'] = package_digest(package)
            try:
                self.store.save_exam(package, question_pack=qs, assistance_level=p['allowed_assistance_level'])
            except StoreError as exc:
                return self._failure('STORE', exc.code, model_calls=calls)
        result = {'ok': True, 'terminal_status': output['terminal_status'], 'model_calls': calls,
                  'learner_visible_payload': None, 'engine_output': output, 'validation': {'pre': True, 'post': True}}
        if deliver and qs:
            delivered = self.delivery.deliver_initial(p, output, exam_id=exam_id, attempt_id=attempt_id)
            result.update({k: delivered[k] for k in ['ok', 'learner_visible_payload', 'error_code']})
            result['stage'] = 'DELIVERY'
            result['disclosure_state'] = delivered.get('disclosure_state')
            if delivered.get('terminal_status'):
                result['terminal_status'] = delivered['terminal_status']
                blocked = copy.deepcopy(output)
                blocked.update(terminal_status=delivered['terminal_status'],
                               error_code=delivered['error_code'],
                               error_detail='Delivery blocked by pedagogical safety review.',
                               learner_visible_payload=None)
                blocked['scope_evaluation']['prior_assistance_preserved'] = True
                for key in ('socratic_questions', 'response_observations',
                            'unverified_observations_requiring_review'):
                    blocked['orchestrator_only_payload'][key] = []
                result['engine_output'] = blocked
        return result

    def run_doc_defense(self, payload, *, batch_exam_id: str, turn_id: str, deliver: bool = False) -> dict:
        try:
            parsed = strict_json(payload)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            parsed = {}
        session_id = parsed.get('defense_session_id')
        if not session_id and isinstance(parsed.get('session_state_snapshot'), dict):
            session_id = parsed['session_state_snapshot'].get('defense_session_id')
        session_state = self.store.get_doc_session_state(session_id) if isinstance(session_id, str) else None
        prior = parsed.get('prior_defense_batch_package')
        registry = {}
        resp_registry = {}
        if isinstance(prior, dict):
            prior_bid = prior.get('batch_exam_id', '')
            trusted = self.delivered_doc_batch(prior_bid)
            if trusted:
                registry[trusted['batch_exam_id']] = trusted
            if isinstance(session_id, str) and isinstance(prior_bid, str):
                resp_registry = self.store.get_doc_responses(session_id, batch_exam_id=prior_bid)
        pre = self.validator.preflight_doc_defense(
            payload, batch_registry=registry, session_state=session_state, response_registry=resp_registry)
        if not pre['ok']:
            return self._failure('PRE', pre['error_code'], terminal_status=pre['terminal_status'], validation=pre)
        p = pre['payload']
        calls = 0
        checked = None
        repair = None
        for _ in range(2):
            try:
                calls += 1
                if hasattr(self.backend, 'generate'):
                    generated = self.backend.generate(p, repair=repair)
                else:
                    generated = self.backend(p)
                session_state = self.store.get_doc_session_state(p['defense_session_id'])
                registry = {}
                resp_registry = {}
                if isinstance(p.get('prior_defense_batch_package'), dict):
                    prior_bid = p['prior_defense_batch_package']['batch_exam_id']
                    trusted = self.delivered_doc_batch(prior_bid)
                    if trusted:
                        registry[trusted['batch_exam_id']] = trusted
                    resp_registry = self.store.get_doc_responses(p['defense_session_id'], batch_exam_id=prior_bid)
                current = self.validator.preflight_doc_defense(
                    p, batch_registry=registry, session_state=session_state, response_registry=resp_registry)
                if not current['ok']:
                    return self._failure('POST', current['error_code'], validation=current, model_calls=calls)
                checked = self.validator.postflight_doc_defense(
                    p, generated, batch_registry=registry, session_state=session_state, response_registry=resp_registry)
            except BackendError as exc:
                return self._failure('MODEL', str(exc), model_calls=calls)
            if checked['ok']:
                break
            if checked.get('rule') != 'DOC-POST-01' or repair is not None:
                return self._failure('POST', checked['error_code'], validation=checked, model_calls=calls)
            repair = {'rule': 'DOC-POST-01', 'error_code': checked['error_code'],
                      'schema_errors': checked.get('schema_errors', []),
                      'instruction': 'One format repair only. Return the full raw JSON object.'}
        if not checked or not checked['ok']:
            return self._failure('POST', (checked or {}).get('error_code', 'INVALID_OUTPUT_SCHEMA'), validation=checked, model_calls=calls)

        final_state = self.store.get_doc_session_state(p['defense_session_id'])
        final_registry = {}
        final_resp_registry = {}
        if isinstance(p.get('prior_defense_batch_package'), dict):
            prior_bid = p['prior_defense_batch_package']['batch_exam_id']
            trusted = self.delivered_doc_batch(prior_bid)
            if trusted:
                final_registry[trusted['batch_exam_id']] = trusted
            final_resp_registry = self.store.get_doc_responses(p['defense_session_id'], batch_exam_id=prior_bid)
        current = self.validator.preflight_doc_defense(
            p, batch_registry=final_registry, session_state=final_state, response_registry=final_resp_registry)
        if not current['ok']:
            return self._failure('POST', current['error_code'], validation=current, model_calls=calls)

        output = checked['output']
        qs = output['orchestrator_only_payload']['defense_questions']
        obs = output['orchestrator_only_payload']['defense_response_observations']
        doc = p['document_descriptor']

        if qs:
            registered = []
            for q in qs:
                registered.append({
                    'question_id': q['question_id'],
                    'parent_question_id': None,
                    'section_id': q['section_id'],
                    'passage_id': q['passage_id'],
                    'target_dimension': q['target_dimension'],
                    'claim_epistemic_status': q['claim_epistemic_status'],
                    'delivered_to_learner': False,
                    'voided': False,
                    'defense_record_closed': False,
                    'immutable_criteria': copy.deepcopy(q['expected_explanation_criteria']),
                })
            package = {
                'batch_exam_id': batch_exam_id,
                'defense_session_id': p['defense_session_id'],
                'project_id': p['project_id'],
                'document_id': doc['document_id'],
                'document_version': doc['document_version'],
                'document_sha256': doc['document_sha256'],
                'created_as_of': p['as_of'],
                'registered_questions': registered,
            }
            package['batch_package_sha256'] = doc_package_digest(package)
            try:
                self.store.save_doc_batch(
                    package, question_pack=qs,
                    assistance_level=p['allowed_assistance_level'],
                    batch_index=doc['batch_index'],
                    section_inventory=p['full_section_inventory'])
            except StoreError as exc:
                return self._failure('STORE', exc.code, model_calls=calls)
        elif obs:
            try:
                updated_state = self.store.apply_doc_analysis_outcomes(
                    p['defense_session_id'],
                    batch_exam_id=p['prior_defense_batch_package']['batch_exam_id'],
                    output=output,
                    turn_id=turn_id,
                    expected_responses=p['defense_responses'],
                )
            except StoreError as exc:
                return self._failure('STORE', exc.code, model_calls=calls)

        result = {
            'ok': True,
            'terminal_status': output['terminal_status'],
            'model_calls': calls,
            'learner_visible_payload': None,
            'engine_output': output,
            'validation': {'pre': True, 'post': True},
            'session_state_snapshot': self.store.get_doc_session_state(p['defense_session_id']),
        }

        if deliver and qs:
            delivered = self.delivery.deliver_doc_initial(p, output, batch_exam_id=batch_exam_id, turn_id=turn_id)
            result.update({k: delivered[k] for k in ['ok', 'learner_visible_payload', 'error_code']})
            result['stage'] = 'DELIVERY'
            result['session_state_snapshot'] = delivered.get('session_state_snapshot')
            if delivered.get('terminal_status'):
                result['terminal_status'] = delivered['terminal_status']
                blocked = copy.deepcopy(output)
                blocked.update(terminal_status=delivered['terminal_status'],
                               error_code=delivered['error_code'],
                               error_detail='Delivery blocked by pedagogical safety review.',
                               learner_visible_payload=None)
                blocked['project_defense_scope_evaluation']['prior_assistance_preserved'] = True
                blocked['orchestrator_only_payload']['defense_questions'] = []
                blocked['orchestrator_only_payload']['defense_response_observations'] = []
                result['engine_output'] = blocked
        elif deliver and obs:
            first_fq = next((o['followup_question'] for o in obs if o.get('followup_question')), None)
            if first_fq:
                refreshed_p = copy.deepcopy(p)
                refreshed_p['session_state_snapshot'] = self.store.get_doc_session_state(p['defense_session_id'])
                delivered = self.delivery.deliver_doc_followup(
                    refreshed_p,
                    batch_exam_id=p['prior_defense_batch_package']['batch_exam_id'],
                    turn_id=turn_id,
                    followup_question_id=first_fq['followup_question_id'],
                )
                result.update({k: delivered[k] for k in ['ok', 'learner_visible_payload', 'error_code']})
                result['stage'] = 'DELIVERY'
                result['session_state_snapshot'] = delivered.get('session_state_snapshot')
        return result

    @staticmethod
    def public_result(result: dict) -> dict:
        """No private rubric, engine text or raw validation evidence in default CLI output."""
        keys = {'ok', 'stage', 'error_code', 'terminal_status', 'model_calls', 'learner_visible_payload'}
        return {key: value for key, value in result.items() if key in keys}
