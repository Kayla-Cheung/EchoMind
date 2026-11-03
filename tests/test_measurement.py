"""Source-v2 regression tests: isolated databases and fake transports only."""
import copy
import csv
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from echomind import measurement as m
from echomind.design import initial_design
from echomind.history import batch_report
from echomind.model_client import ProviderError, build_request, make_spec
from echomind.prompt_registry import BUILTINS, MULTIAXIS_SCHEMA, catalog, save_bundle
from echomind.runner import JobManager, execute_task, plan
from echomind.storage import Store


def request(**kwargs):
    return {"protocol": m.PROTOCOL_ID, "mode": "mock", "models": [{"provider": "deepseek"}],
            "evaluator": {"provider": "deepseek"}, "repeats": 3, "concurrency": 1, **kwargs}


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'temp.sqlite3')

    def prepare(self, req=None):
        req = copy.deepcopy(req or request())
        settings = plan(self.store.design(), req, prompt_bundles=catalog(self.store))
        req['preview_hash'] = settings['preview_hash']
        return req, settings

    def wait_job(self, manager, job):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            finished = manager.get(job['id'])
            if finished['status'] not in ('queued', 'running'):
                return finished
            time.sleep(.02)
        self.fail('background job did not finish')

    def run_mock(self, req=None):
        req, settings = self.prepare(req)
        manager = JobManager(self.store)
        with patch('echomind.runner.call', side_effect=AssertionError('MOCK must not call any API')):
            job = self.wait_job(manager, manager.start(req))
        self.assertEqual(job['status'], 'complete')
        return job, self.store.trials()

    def test_factorial_matching_and_blind_prompt(self):
        _, p = self.prepare(request(scenario_ids=[s['id'] for s in m.SCENARIOS], material_ids=['M1', 'M2']))
        self.assertEqual(p['calls'], 192)
        self.assertEqual(len(m.preview_plan(p)['examples']), 64)
        for mat in ['M1', 'M2']:
            for valence in ['benign', 'adverse']:
                pair = [t for t in p['tasks'] if t['material_id'] == mat and t['memory_valence'] == valence
                        and t['scenario']['id'] == 'V2S01' and t['repeat'] == 1 and t['bundle']['version'] == BUILTINS[0]['version']]
                self.assertEqual(len(pair), 2)
                self.assertEqual(pair[0]['events'], pair[1]['events'])
                prompts = [m.render(t, p['measurement_config']['identity'], 'RESPONSE') for t in pair]
                self.assertNotEqual(prompts[0]['role_messages'], prompts[1]['role_messages'])
                self.assertEqual(prompts[0]['evaluator_messages'], prompts[1]['evaluator_messages'])
                self.assertNotIn(pair[0]['events'], json.dumps(prompts[0]['evaluator_messages'], ensure_ascii=False))
        for bad in [request(material_ids=['missing']), request(conditions=['self_adverse']), request(prompt_versions=[]), request(scenario_ids=['V2S01','V2S01'])]:
            with self.assertRaises(ValueError): self.prepare(bad)

    def test_preview_is_readonly_and_configuration_must_match(self):
        req, p = self.prepare()
        m.preview_plan(p)
        self.assertEqual(self.store.trials(), [])
        manager = JobManager(self.store)
        with self.assertRaises(ValueError): manager.start(request())
        req['repeats'] = 2
        with self.assertRaises(ValueError): manager.start(req)
        self.assertEqual(self.store.trials(), [])
        req, _ = self.prepare()
        design = self.store.design(); design['identity']['name'] = 'changed'
        self.store.save_design(design)
        with self.assertRaises(ValueError): manager.start(req)

    def test_mock_history_persistence_no_old_rewrite_or_fake_effect(self):
        old = {'id':'old','timestamp':'2026-01-01T00:00:00Z','source':'MOCK_NOT_LLM','status':'complete','protocol':'memory-ratio-v1','batch_id':'old'}
        self.store.add_trial(old)
        with self.store.connection() as db:
            before = db.execute("SELECT payload FROM trials WHERE id='old'").fetchone()[0]
        job, rows = self.run_mock()
        report = m.summarize(rows, job['id'], job)
        self.assertEqual(report['recorded'], 24)
        self.assertIn('MOCK', report['evidence_status'])
        self.assertTrue(all(s['source_interaction'] == 0 for s in report['strata']))
        for s in report['strata']:
            for c in s['cells']:
                self.assertEqual((c['negative_present'], c['both_present'], c['immediate_withdraw']), (2,1,1))
        self.assertIn('measurement_report', batch_report(rows,job['id']))
        self.assertEqual(JobManager(Store(self.store.path)).get(job['id']),job)
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT payload FROM trials WHERE id='old'").fetchone()[0], before)

    def test_multiaxis_schema_sent_instead_of_legacy_schema(self):
        spec = make_spec({'provider':'openai'})
        args = [{'role':'user','content':'test'}]
        legacy = build_request(spec,args,evaluator=True)['text']['format']['schema']
        new = build_request(spec,args,evaluator=True,coding_schema=MULTIAXIS_SCHEMA)['text']['format']['schema']
        self.assertIn('interpretation',legacy['properties'])
        self.assertNotIn('interpretation',new['properties'])
        self.assertIn('negative_attribution',new['properties'])

    def test_saved_custom_prompt_used_and_frozen(self):
        bundle = copy.deepcopy(BUILTINS[0]); bundle.update(version='agent-custom-test-v2.1', parent=BUILTINS[0]['version'])
        bundle['agent_user'] += '\nUNIQUE_TEMPLATE_MARKER'
        saved = save_bundle(self.store,bundle)
        job, rows = self.run_mock(request(prompt_versions=[saved['version']],repeats=1))
        self.assertEqual(len(rows),4)
        self.assertTrue(all('UNIQUE_TEMPLATE_MARKER' in r['role_messages'][1]['content'] for r in rows))
        self.assertTrue(all(r['bundle_hash'] == saved['content_hash'] for r in rows))
        coder = {**bundle, 'version':'coder-changed-test-v2.1','coder_version':'coder-test-v4','coder_user':bundle['coder_user']+'\nChanged.'}
        changed = save_bundle(self.store,coder)
        with self.assertRaises(ValueError): self.prepare(request(prompt_versions=[saved['version'],changed['version']]))

    def test_fake_live_raw_evidence_and_coder_schema(self):
        _, p = self.prepare(request(mode='live',repeats=1))
        task = p['tasks'][0]
        response, coding = m.mock_result(task)
        with patch('echomind.runner.call',side_effect=[(response,{}),(json.dumps(coding),{})]) as fake:
            row = execute_task(self.store,initial_design(),task,p,'fake',threading.Event())
        self.assertEqual(row['status'],'complete')
        self.assertEqual(fake.call_args_list[1].kwargs['coding_schema'],MULTIAXIS_SCHEMA)
        self.assertEqual(row['evaluator_raw'],json.dumps(coding))
        self.assertEqual(row['machine_coding'],coding)

    def test_failed_coder_preserves_response_and_unknown_denominator(self):
        _, p = self.prepare(request(mode='live',repeats=1))
        task = p['tasks'][0]
        response, coding = m.mock_result(task)
        coding['benign_attribution']={'value':'present','evidence':['invented absent quotation']}
        with patch('echomind.runner.call',side_effect=[(response,{}),(json.dumps(coding),{})]):
            row = execute_task(self.store,initial_design(),task,p,'invalid',threading.Event())
        self.assertEqual(row['status'],'error')
        self.assertEqual(row['narrative'],response)
        self.assertEqual(row['evaluator_raw'],json.dumps(coding))
        report = m.summarize(self.store.trials(),'invalid')
        cell = next(c for c in report['strata'][0]['cells'] if c['recorded'])
        self.assertEqual((cell['response_n'],cell['negative_unknown'],cell['negative_bounds']),(1,1,[0,1]))
        self.assertIsNone(report['strata'][0]['source_interaction'])

    def test_authentication_stop_on_new_protocol_and_offline_guard(self):
        req, _ = self.prepare(request(mode='live',repeats=1))
        manager = JobManager(self.store)
        with patch('echomind.runner.offline_mode',return_value=True):
            with self.assertRaises(ValueError): manager.start(req)
        with patch('echomind.runner.offline_mode',return_value=False), patch('echomind.runner.call',side_effect=ProviderError('fake auth','authentication')) as fake:
            job = self.wait_job(manager, manager.start(req))
        self.assertEqual(fake.call_count,1)
        self.assertEqual(job['unissued'],7)
        self.assertEqual(job['stop_reason'],'authentication')

    def test_partial_unknown_conditional_actions_and_protocol_isolation(self):
        job, rows = self.run_mock()
        row = rows[0]
        code = row['machine_coding']
        code['negative_attribution']={'value':'uncertain','evidence':[]}
        code['negative_commitment']='uncertain'
        for action in code['actions']:
            action.update(kind='withdraw',timing='conditional')
        report = m.summarize(rows,job['id'])
        changed = next(s for s in report['strata'] if s['output_format'] == row['output_format'])
        self.assertIsNone(changed['source_interaction'])
        cell = next(c for c in changed['cells'] if c['condition']==row['condition'])
        self.assertEqual(cell['negative_unknown'],1)
        self.assertEqual(cell['conditional_withdraw'],1)
        with self.assertRaises(ValueError): m.summarize(rows+[{'batch_id':job['id'],'protocol':'memory-ratio-v1'}],job['id'])

    def test_blank_review_is_blind_and_mapping_stable(self):
        job, rows = self.run_mock(request(repeats=1))
        first, second = m.review_pack(rows,job['id']),m.review_pack(rows,job['id'])
        sheet = list(csv.DictReader(io.StringIO(first['csv'].lstrip('\ufeff'))))
        self.assertEqual(len(sheet),8)
        self.assertEqual({x['case_id'] for x in first['key']},{x['case_id'] for x in second['key']})
        self.assertTrue(all(not x['negative_attribution'] and not x['reviewer_id'] for x in sheet))
        for hidden in ['condition','model','protocol','machine_coding','trial_id']:
            self.assertNotIn(hidden,sheet[0])


class MeasurementHTTP(unittest.TestCase):
    def test_preview_run_export_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def api(path,data=None,raw=False):
                r=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
                with opener.open(r,timeout=5) as response: text=response.read().decode('utf-8-sig')
                return text if raw else json.loads(text)
            def start():
                proc=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--offline','--port',str(port)],cwd=folder,
                    env={**os.environ,'ECHOMIND_OFFLINE':'1','ECHOMIND_PILOT_DB':str(Path(folder)/'temp.sqlite3')},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(80):
                    try: api('/api/measurement/bootstrap');return proc
                    except OSError:time.sleep(.05)
                proc.terminate();proc.wait();self.fail('server not ready')
            proc=start()
            try:
                self.assertTrue(api('/api/measurement/bootstrap')['offline'])
                req=request(repeats=1);preview=api('/api/measurement/preview',req)
                self.assertEqual(preview['role_calls'],8)
                self.assertEqual(api('/api/history/batches')['total_records'],0)
                job=api('/api/jobs',{**req,'preview_hash':preview['preview_hash']})
                for _ in range(100):
                    finished=api('/api/jobs/'+job['id'])
                    if finished['status'] not in ('queued','running'):break
                    time.sleep(.04)
                self.assertEqual((finished['status'],finished['completed']),('complete',8))
                suffix='?batch_id='+job['id']
                report=api('/api/measurement/export.json'+suffix)
                self.assertEqual(len(report['records']),8)
                self.assertEqual(api('/api/trials'),[])
                self.assertIn('measurement_report',api('/api/history/batch'+suffix))
                csvrows=list(csv.DictReader(io.StringIO(api('/api/history/export.csv'+suffix,raw=True))))
                self.assertEqual(json.loads(csvrows[0]['record_json']),report['records'][0])
                self.assertEqual(csvrows[0]['negative_attribution'],'absent')
                self.assertEqual(len(api('/api/review/key.json'+suffix)['mapping']),8)
                self.assertIn('negative_evidence',api('/api/review/export.csv'+suffix,raw=True))
                proc.terminate();proc.wait(timeout=5);proc=start()
                self.assertEqual(api('/api/measurement/report'+suffix)['records'],report['records'])
                self.assertEqual(api('/api/jobs/'+job['id']),finished)
                self.assertEqual(api('/api/measurement/bootstrap')['jobs'],[finished])
            finally:
                if proc.poll() is None:proc.terminate();proc.wait(timeout=5)


if __name__ == '__main__': unittest.main()
