"""CLI/HTTP integration tests: no credentials, Codex, or live models required."""
import copy
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

from project_auditor_runtime.backend import HTTPBackend, BackendError, provider_schema
from project_auditor_runtime.cli import main, InteractiveSession, show_public, SessionError
from project_auditor_runtime.packaging import package_source, digest
from project_auditor_runtime.runner import ProjectAuditorRuntime
from project_auditor_runtime.validation import extract_schemas, extract_doc_defense_schemas, RuntimeValidator
from project_auditor_runtime.delivery import DOC_NOTICE_HINTS, DOC_NOTICE_PARTIAL

ROOT = Path(__file__).resolve().parents[2]
SPECS = ROOT / 'specs'


def blocks(name):
    return [json.loads(x) for x in re.findall(r'^```json\s*\n(.*?)^```\s*$',
            (SPECS / name).read_text(encoding='utf-8-sig'), re.M | re.S)]


DOC = blocks('PROJECT_DEFENSE_CONTRACT.md')


def safe_review(context):
    return {'reveals_expected_answer': False, 'determines_solution_steps': False,
            'combined_context_completes_solution': False, 'reveals_unfound_diagnosis': False}


class DynamicBackend:
    """Small deterministic model double exercising real PRE/POST/SQLite/delivery."""
    review = staticmethod(safe_review)

    def __init__(self, mode='normal', invalid_first=False):
        self.mode, self.invalid_first = mode, invalid_first
        self.repairs = []
        self.questions = {}

    def generate(self, p, repair=None):
        self.repairs.append(repair)
        if self.invalid_first and len(self.repairs) == 1:
            return '{}'
        o = copy.deepcopy(DOC[3])
        o.update(task_id=p['task_id'], as_of_evaluated=p['as_of'], operation_evaluated=p['operation'])
        d = p['document_descriptor']
        s = o['project_defense_scope_evaluation']
        s.update(project_id=p['project_id'], defense_session_id=p['defense_session_id'], document_id=d['document_id'],
                 document_version_evaluated=d['document_version'], document_sha256_evaluated=d['document_sha256'],
                 document_type_evaluated=d['document_type'], evaluated_domain=p['learning_domain'],
                 allowed_assistance_level_evaluated=p['allowed_assistance_level'], batch_index_evaluated=d['batch_index'],
                 total_batches_evaluated=d['total_batches'],
                 inspected_section_ids_in_batch=[x['section_id'] for x in p['full_section_inventory'] if x['in_current_batch']],
                 uninspected_section_ids=[x['section_id'] for x in p['full_section_inventory'] if not x['in_current_batch']],
                 waiting_visual_section_ids=[], missing_contribution_fields_to_ask=p['contribution_context']['missing_contribution_fields'])
        o['section_dimension_matrix'] = [dict(section_id=x['section_id'], dimension=z['dimension'], status=z['status'],
                                             status_reason='AWAITING_BATCH_OR_QUESTION')
                                        for x in p['full_section_inventory'] for z in x['prior_dimension_statuses']]
        o['analysis_limitations'] = []
        for x in p['current_batch_passages']:
            if x['claim_epistemic_status'] in ('PLAN', 'IDEA'):
                o['analysis_limitations'].append(dict(limitation_code='UNIMPLEMENTED_OR_IDEA_ONLY_CLAIM',
                    section_id=x['section_id'], passage_id=x['passage_id'], detail='No measured result verified.'))
        if s['uninspected_section_ids']:
            o['analysis_limitations'].append(dict(limitation_code='UNINSPECTED_BATCH_SECTIONS_REMAIN',
                section_id=s['uninspected_section_ids'][0], passage_id=None, detail='Later batch.'))
        priv = o['orchestrator_only_payload']
        priv['defense_questions'] = []
        priv['defense_response_observations'] = []
        summary = priv['defense_outcome_summary']
        summary['open_dimensions'] = [dict(section_id=m['section_id'], dimension=m['dimension'], open_reason='Awaiting explanation.')
                                      for m in o['section_dimension_matrix']]
        if p['operation'] == 'PREPARE_PROJECT_DEFENSE':
            partial = bool(s['uninspected_section_ids'])
            o['terminal_status'] = 'PARTIAL_PROJECT_DEFENSE_PREPARED' if partial else 'PROJECT_DEFENSE_PREPARED'
            x = p['current_batch_passages'][0]
            n = 1
            batch_index = d['batch_index']
            q = copy.deepcopy(DOC[3]['orchestrator_only_payload']['defense_questions'][0])
            q.update(question_id=f'DQ-{n:02d}-METHOD_B{batch_index:02d}', section_id=x['section_id'], passage_id=x['passage_id'],
                     heading_path=x['heading_path'], claim_epistemic_status=x['claim_epistemic_status'],
                     evidence_basis=x['evidence_basis'], cross_section_refs=[], target_dimension='METHOD',
                     neutral_question_prompt='Why does this approach fit your input?', addresses_missing_contribution=True,
                     expected_explanation_criteria=[dict(criterion_id=f'DCRIT-Q{n:02d}-01',
                         criterion_text='PRIVATE: explain the input boundary rationale.', required_depth='TRADEOFF_JUSTIFICATION')],
                     on_demand_hints=[dict(hint_id=f'DH-{n:02d}-01-BOUNDARY_B{batch_index:02d}', hint_order=1,
                         conceptual_nudge='Consider the input boundary.')])
            self.questions[q['question_id']] = q
            priv['defense_questions'] = [q]
            public_q = {k: v for k, v in q.items() if k in ('question_id','section_id','passage_id','heading_path','target_dimension','claim_epistemic_status','neutral_question_prompt')}
            o['learner_visible_payload'] = dict(canonical_initial_question_id=q['question_id'], initial_neutral_question=public_q,
                uninspected_section_ids=s['uninspected_section_ids'], waiting_visual_section_ids=[],
                active_scope_notice=DOC_NOTICE_PARTIAL if partial else DOC_NOTICE_HINTS)
        else:
            o['terminal_status'] = 'PROJECT_DEFENSE_ANALYZED'
            o['learner_visible_payload'] = None
            r = p['defense_responses'][0]
            q = self.questions[r['parent_question_id'] or r['question_id']]
            obs = copy.deepcopy(DOC[5]['orchestrator_only_payload']['defense_response_observations'][0])
            obs.update({k:r[k] for k in ('response_id','turn_id','question_id','parent_question_id','section_id','passage_id','target_dimension')})
            obs.update(evaluation_verdict='IDK_DECLARED_READY_FOR_TEACHING' if r['is_idk_declaration'] else 'FLUENT_SUPERFICIAL_OR_EMPTY',
                       assistance_classification_for_response='NOT_EXPLAINED', followup_question=None)
            obs['criterion_evaluations'] = [dict(criterion_id=c['criterion_id'], criterion_text=c['criterion_text'],
                status='NOT_DEMONSTRATED' if r['is_idk_declaration'] else 'PARTIAL_OR_VAGUE',
                verbatim_response_excerpt=r['raw_response_text'], observation_note='More explanation needed.') for c in q['expected_explanation_criteria']]
            if r['is_idk_declaration']:
                obs['teaching_transition_packet'] = dict(teaching_packet_id='TEACH-CLI-01', closed_question_id=r['question_id'],
                    closed_response_id=r['response_id'], section_id=r['section_id'], target_dimension=r['target_dimension'],
                    concept_and_rationale_explanation='An input boundary describes the values an approach can handle.',
                    suggested_approaches=['Compare typical inputs with a boundary case.'], downstream_affected_dimensions=[])
            elif self.mode == 'followup' and not r['parent_question_id']:
                obs['evaluation_verdict'] = 'VAGUE_OR_INCOMPLETE_NEEDS_FOLLOWUP'
                obs['followup_question'] = dict(followup_question_id='FQ-'+q['question_id']+'-01', parent_question_id=q['question_id'],
                    section_id=r['section_id'], passage_id=r['passage_id'], target_dimension=r['target_dimension'],
                    followup_reason='CLARIFY_VAGUE_RESPONSE', neutral_followup_prompt='Can you clarify the input boundary?')
            priv['defense_response_observations'] = [obs]
        return json.dumps(o)


class PackagingTests(unittest.TestCase):
    def test_code_hash_lines_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'demo.py'
            raw = b'print(1)\r\n\r\ndef example():\r\n    return 2\r\n'
            p.write_bytes(raw)
            pkt = package_source(p, code=True)
            self.assertEqual(pkt['source_sha256'], digest(raw))
            self.assertEqual(pkt['line_map'][0]['start_line'], 1)
            self.assertEqual(pkt['line_map'][-1]['end_line'], 4)
            self.assertEqual(''.join(x['verbatim_text'] for x in pkt['passages']), raw.decode().replace('\r\n','\n'))
            self.assertEqual(p.read_bytes(), raw)
            self.assertFalse(pkt['request']['tool_permissions']['code_execution_allowed'])

    def test_document_headings_fences_images_and_batching(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'README.md'
            p.write_text('# Design\n```python\n# not a heading\n```\n![chart](chart.png)\n' + ''.join(f'## Section {i}\nText.\n' for i in range(5)), encoding='utf-8')
            pkt=package_source(p)
            self.assertEqual(len(pkt['passages']), 6)
            self.assertTrue(pkt['request']['full_section_inventory'][0]['has_unreadable_visuals'])
            self.assertEqual(pkt['request']['document_descriptor']['total_batches'], 2)
            self.assertEqual(pkt['request']['contribution_context']['team_structure'], 'UNKNOWN')

    def test_reject_empty_binary_long_line_and_c(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'demo.py'
            for raw in (b'', b'\x00binary', b'\xff', b'x'*6001):
                p.write_bytes(raw)
                with self.assertRaises((ValueError, UnicodeError)): package_source(p, code=True)
            p=Path(tmp)/'main.c'; p.write_text('int main(){}')
            with self.assertRaises(ValueError): package_source(p, code=True)

    def test_dry_run_no_backend_or_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'demo.py'; p.write_text('print(1)\n')
            state=Path(tmp)/'state'
            out=io.StringIO()
            with redirect_stdout(out), patch('project_auditor_runtime.cli.create_backend') as backend:
                self.assertEqual(main(['--file',str(p),'--state-dir',str(state),'--dry-run']),0)
            self.assertFalse(state.exists()); backend.assert_not_called()
            self.assertTrue(json.loads(out.getvalue())['line_map'])


class HTTPTests(unittest.TestCase):
    def invoke(self, provider, envelope, schema=None, data=None):
        self.opener=MagicMock()
        self.opener.open.return_value.__enter__.return_value.read.return_value=json.dumps(envelope).encode()
        with patch('urllib.request.build_opener',return_value=self.opener), patch.dict(os.environ, {
            'GEMINI_API_KEY':'secret-test','OPENAI_API_KEY':'secret-test','OPENROUTER_API_KEY':'secret-test'}, clear=True):
            return HTTPBackend(SPECS,provider=provider,model='test-model')._invoke('system',data or {},schema or {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']})

    def test_each_provider_wires_both_output_schemas(self):
        for provider in HTTPBackend.PROVIDERS:
            for extractor in (extract_schemas,extract_doc_defense_schemas):
                with self.subTest(provider=provider,schema=extractor.__name__):
                    schema=extractor(SPECS)[1]
                    envelope=({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{}'}]}}]} if provider=='gemini' else
                              {'message':{'content':'{}'},'done':True} if provider=='ollama' else
                              {'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
                    self.assertEqual(self.invoke(provider,envelope,schema),'{}')
                    req=self.opener.open.call_args.args[0]
                    body=json.loads(req.data)
                    actual=(body['generationConfig']['responseJsonSchema'] if provider=='gemini' else
                            body['format'] if provider=='ollama' else body['response_format']['json_schema']['schema'])
                    self.assertEqual(actual,provider_schema(schema))
                    self.assertEqual(actual['properties']['schema_version']['enum'],[schema['properties']['schema_version']['const']])
                    self.assertEqual(body.get('stream',False),False)
                    self.assertNotIn('tools',body)
                    if provider=='ollama': self.assertEqual(req.full_url,'http://localhost:11434/api/chat')

    def test_generate_supplies_schema_and_repair_to_http(self):
        for provider in HTTPBackend.PROVIDERS:
            for payload in (blocks('CONTRACT.md')[2],DOC[2]):
                backend=HTTPBackend(SPECS,provider=provider,model='test')
                with patch.object(backend,'_invoke',return_value='{}') as invoke:
                    backend.generate(payload,repair={'rule':'POST-01'})
                instructions,data,schema=invoke.call_args.args
                self.assertEqual(data['single_repair_request']['rule'],'POST-01')
                self.assertIn('schema_version',schema['properties'])
                self.assertIn('AUTHORITATIVE OUTPUT JSON SCHEMA',instructions)

    def test_refusal_tool_calls_truncation_and_bad_envelopes_fail_closed(self):
        for message, finish in [({'content':'{}','refusal':'no'},'stop'),({'content':'{}','tool_calls':[{}]},'stop'),({'content':'{}'},'length'),({},'stop')]:
            with self.subTest(message=message,finish=finish), self.assertRaises(BackendError):
                self.invoke('openai',{'choices':[{'finish_reason':finish,'message':message}]})
        with self.assertRaises(BackendError): self.invoke('gemini',{'candidates':[]})
        with self.assertRaises(BackendError): self.invoke('ollama',{'message':{'content':'{}'},'done':False})

    def test_missing_key_and_errors_never_print_credentials(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(BackendError,'OPENAI_API_KEY_MISSING'):
                HTTPBackend(SPECS,provider='openai',model='test')._invoke('',{}, {})
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'secret\nheader'}, clear=True):
            with self.assertRaisesRegex(BackendError, '^INVALID_API_KEY$'):
                HTTPBackend(SPECS,provider='openai',model='test')._invoke('', {}, {})
        for failure in (HTTPError('http://secret',429,'secret',{},None),URLError('secret')):
            opener=MagicMock(); opener.open.side_effect=failure
            with patch('urllib.request.build_opener',return_value=opener), self.assertRaises(BackendError) as ctx:
                HTTPBackend(SPECS,provider='ollama',model='test')._invoke('',{}, {})
            self.assertNotIn('secret',str(ctx.exception))


class InteractiveTests(unittest.TestCase):
    def session(self, answers, *, code=False, mode='normal', invalid_first=False, sections=1):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/('demo.py' if code else 'README.md')
            path.write_text('print(1)\n' if code else ''.join(f'# Topic {i}\nThe approach accepts static inputs.\n' for i in range(sections)),encoding='utf-8')
            packet=package_source(path,code=code)
            backend=DynamicBackend(mode,invalid_first)
            runtime=ProjectAuditorRuntime(ROOT,Path(tmp)/'state',backend=backend)
            output=[]; iterator=iter(answers)
            InteractiveSession(runtime,packet,read=lambda _:next(iterator),write=output.append).run()
            sid=packet['request']['defense_session_id']
            snapshot=runtime.store.get_doc_session_state(sid)
            disclosed=runtime.store.get_doc_disclosed_context(sid)
            self.assertNotIn('PRIVATE:', '\n'.join(output))
            return output,snapshot,disclosed,backend

    def test_file_and_doc_questions_answers_finish(self):
        for code in (True,False):
            with self.subTest(code=code):
                out,state,events,_=self.session(['Some rationale.'],code=code)
                self.assertEqual(state['session_status'],'STOPPED_BY_USER')
                self.assertTrue(any('Response:' in x for x in out))

    def test_hint_idk_teaching_is_recorded(self):
        out,state,events,_=self.session(['/hint','bilmiyorum'])
        self.assertTrue(state['disclosed_hint_ids'])
        self.assertTrue(state['taught_dimensions'])
        self.assertTrue(any('An input boundary' in x for x in out))

    def test_followup_response_is_analyzed(self):
        out,state,events,_=self.session(['Unclear.','A little clearer.'],mode='followup')
        self.assertTrue(any('Can you clarify' in x for x in out))
        self.assertEqual(state['session_status'],'STOPPED_BY_USER')

    def test_quit_pause_and_schema_repair(self):
        out,state,events,backend=self.session(['/quit'],invalid_first=True)
        self.assertEqual(state['session_status'],'PAUSED')
        self.assertEqual(len(backend.repairs),2)
        self.assertEqual(backend.repairs[1]['rule'],'DOC-POST-01')

    def test_multiple_batches(self):
        out,state,events,_=self.session(['First answer.','Second answer.'],sections=5)
        self.assertEqual(state['session_status'],'STOPPED_BY_USER')

    def test_public_renderer_never_dumps_private_data(self):
        out=[]
        show_public({'engine_output':{'criteria':'PRIVATE'},'learner_visible_payload':{'unknown':'PRIVATE','conceptual_nudge':'safe'}},out.append)
        self.assertEqual(out,['safe'])

    def test_installed_cli_real_http_with_hint_and_teaching(self):
        backend = DynamicBackend()
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append(body)
                data = json.loads(body['messages'][1]['content'].split('<UNTRUSTED_DATA>\n')[1].split('\n</UNTRUSTED_DATA>')[0])
                answer = (backend.generate(data['input_payload'], data.get('single_repair_request'))
                          if 'input_payload' in data else json.dumps(safe_review(data)))
                response = json.dumps({'message': {'content': answer}, 'done': True}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/'demo.py'
                path.write_text('print(1)\n', encoding='utf-8')
                env = os.environ.copy()
                env['OLLAMA_HOST'] = f'http://127.0.0.1:{server.server_port}'
                env['PYTHONIOENCODING'] = 'utf-8'
                result = subprocess.run([sys.executable, '-m', 'project_auditor_runtime.cli',
                    '--file', str(path), '--state-dir', str(Path(tmp)/'state'), '--model', 'test-model'],
                    input='/hint\n/idk\n', text=True, encoding='utf-8', capture_output=True,
                    cwd=tmp, env=env, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn('An input boundary', result.stdout)
                self.assertNotIn('PRIVATE:', result.stdout)
                self.assertTrue(all(isinstance(x['format'], dict) for x in requests))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__=='__main__': unittest.main()
