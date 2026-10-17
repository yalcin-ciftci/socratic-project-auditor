"""Focused parser, trusted-state and semantic-review regressions."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.codex' / 'scripts'))
from project_auditor_runtime.validation import RuntimeValidator, canonical_hash, strict_json

AGENT = ROOT / '🛠️ 600-Arsenal' / 'Ajanlar' / 'proje-denetleyici-ve-ogrenim-sorgulayicisi'


def fixtures(filename):
    return [json.loads(block) for block in re.findall(
        r'^```json\s*\n(.*?)^```\s*$', (AGENT / filename).read_text(encoding='utf-8'), re.M | re.S)]


def safe_review(context):
    return {'early_topic_overreach': False, 'architectural_prerequisites_unverified': False}


@unittest.skipUnless(importlib.util.find_spec('jsonschema') and importlib.util.find_spec('rfc3339_validator'), 'mandatory validator dependencies unavailable')
class ValidatorTests(unittest.TestCase):
    def setUp(self):
        blocks = fixtures('CONTRACT.md')
        self.input = copy.deepcopy(next(b for b in blocks if b.get('schema_version') == 'harmanos.project_auditor.input.v1'))
        self.output = copy.deepcopy(next(b for b in blocks if b.get('schema_version') == 'harmanos.project_auditor.output.v1'))
        self.validator = RuntimeValidator(AGENT, safe_review)
        self.ledger = copy.deepcopy(self.input['disclosure_state'])

    def pre(self, value=None, ledger=None):
        return self.validator.preflight(self.input if value is None else value, exam_registry={}, ledger=self.ledger if ledger is None else ledger)

    def post(self, value=None, validator=None):
        return (validator or self.validator).postflight(self.input, self.output if value is None else value, exam_registry={}, ledger=self.ledger)

    def test_accepted_pairs_pass_with_explicit_semantic_fixture(self):
        self.assertTrue(self.pre()['ok'])
        self.assertTrue(self.post()['ok'])
        blocks = fixtures('PROMPT.md')
        p, o = blocks
        registry = {p['prior_exam_package']['exam_id']: copy.deepcopy(p['prior_exam_package'])}
        self.assertTrue(self.validator.preflight(p, exam_registry=registry, ledger=p['disclosure_state'])['ok'])
        self.assertTrue(self.validator.postflight(p, o, exam_registry=registry, ledger=p['disclosure_state'])['ok'])

    def test_duplicate_key_nonfinite_nonobject_and_lone_surrogate_rejected(self):
        for raw in ('{"task_id":"ABC","task_id":"DEF"}', '{"task_id":"ABC","x":NaN}', '{"task_id":"ABC","x":1e999}', '[]', '{"task_id":"ABC","x":"\\ud800"}', b'\xff'):
            with self.subTest(raw=repr(raw)):
                result = self.pre(raw)
                self.assertFalse(result['ok'])
                self.assertEqual(result['rule'], 'PRE-01')
        for value in ({'task_id': 'ABC', 'x': float('inf')}, {'task_id': 'ABC', 'x': (1, 2)}, {1: 'x'}):
            with self.assertRaises(ValueError):
                strict_json(value)

    def test_normalizes_lf_without_mutating_caller(self):
        original = self.input['code_artifacts'][0]['content']
        self.input['code_artifacts'][0]['content'] = original.replace('\n', '\r\n')
        result = self.pre()
        self.assertTrue(result['ok'])
        self.assertEqual(result['payload']['code_artifacts'][0]['content'], original)
        self.assertIn('\r\n', self.input['code_artifacts'][0]['content'])

    def test_missing_stale_or_edited_trusted_ledger_rejected(self):
        result = self.validator.preflight(self.input, exam_registry={}, ledger=None)
        self.assertEqual(result['rule'], 'PRE-07')
        for key, value in (('ledger_revision', 2), ('assistance_log_present', False), ('disclosed_hint_ids', ['H-01-JOIN'])):
            ledger = copy.deepcopy(self.ledger)
            ledger[key] = value
            self.assertEqual(self.pre(ledger=ledger)['rule'], 'PRE-07')

    def test_semantic_review_missing_raises_no_false_guarantee(self):
        result = self.post(validator=RuntimeValidator(AGENT))
        self.assertEqual(result['error_code'], 'SEMANTIC_REVIEW_REQUIRED')
        for review in ({'early_topic_overreach': False}, {'early_topic_overreach': False, 'architectural_prerequisites_unverified': 0}, {'early_topic_overreach': True, 'architectural_prerequisites_unverified': False}):
            result = self.post(validator=RuntimeValidator(AGENT, lambda context: review))
            self.assertFalse(result['ok'])
        seen = []
        def callback(context):
            seen.append(context)
            context['payload']['task_id'] = 'DO-NOT-MUTATE'
            return safe_review(context)
        self.assertTrue(self.post(validator=RuntimeValidator(AGENT, callback))['ok'])
        self.assertEqual(seen[0]['kind'], 'POST-11_EARLY_TOPIC_EXCLUSION')
        self.assertEqual(self.input['task_id'], 'AUD-20261016-001')

    def test_semantic_reviewer_failure_is_closed(self):
        def broken(context):
            raise RuntimeError('review engine unavailable')
        self.assertEqual(self.post(validator=RuntimeValidator(AGENT, broken))['error_code'], 'SEMANTIC_REVIEW_REQUIRED')

    def test_hints_follow_question_ordinal_and_local_order(self):
        q = self.output['orchestrator_only_payload']['socratic_questions'][1]
        self.assertTrue(q['hint_id'].startswith('H-02-') if 'hint_id' in q else q['on_demand_hints'][0]['hint_id'].startswith('H-02-'))
        q['on_demand_hints'][0]['hint_id'] = 'H-01-WRONG'
        self.assertEqual(self.post()['rule'], 'POST-04')

    def test_hash_recomputed_does_not_replace_local_trust(self):
        blocks = fixtures('PROMPT.md')
        p = copy.deepcopy(blocks[0])
        trusted = copy.deepcopy(p['prior_exam_package'])
        p['prior_exam_package']['registered_questions'][0]['immutable_criteria'][0]['criterion_text'] += ' MUTATED'
        p['prior_exam_package']['exam_package_sha256'] = canonical_hash(p['prior_exam_package'])
        result = self.validator.preflight(p, exam_registry={trusted['exam_id']: trusted}, ledger=p['disclosure_state'])
        self.assertEqual(result['rule'], 'PRE-06')

    def test_output_duplicate_json_key_and_nonfinite_rejected(self):
        raw = json.dumps(self.output)
        duplicate = raw.replace('"schema_version":', '"task_id":"FORGED","schema_version":', 1)
        self.assertEqual(self.post(duplicate)['rule'], 'POST-01')
        self.assertEqual(self.post('{"task_id":"ABC","x":NaN}')['rule'], 'POST-01')

    def test_assistance_lattice_known_hint_survives_missing_log(self):
        self.input['disclosure_state']['assistance_log_present'] = False
        self.input['disclosure_state']['disclosed_hint_ids'] = ['H-01-JOIN']
        result = self.validator.assistance_values(self.input)
        self.assertEqual(result, {'known_disclosed_assistance_class': 'HINT_OR_BRAINSTORMING', 'effective_assistance_floor': 'UNKNOWN_UNVERIFIED', 'eligible_for_independent_attempt_submission': False})
        self.input['disclosure_state']['rubric_or_diagnosis_disclosed'] = True
        self.assertEqual(self.validator.assistance_values(self.input)['effective_assistance_floor'], 'EXTERNAL_REFERENCE_USED')

    def test_question_references_require_complete_snapshot(self):
        ref = self.output['orchestrator_only_payload']['socratic_questions'][0]['source_ref']
        ref['snapshot_id'] = 'sha256:' + '0' * 64
        self.assertEqual(self.post()['rule'], 'POST-05')


if __name__ == '__main__':
    unittest.main()
