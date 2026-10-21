import json
import csv
import io
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis import summarize
from design import initial_design
from prompts import evaluator_messages, role_messages, validate_coding
from runner import JobManager, plan
from model_client import PROVIDERS
from storage import Store


class LogicTests(unittest.TestCase):
    def test_batch_continues_after_one_failed_trial(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Store(Path(temp_dir) / 'batch.sqlite3')
            manager = JobManager(store)
            from runner import mock_output
            def one_failure(task):
                if task['condition'] == 'baseline':
                    raise RuntimeError('simulated trial failure')
                return mock_output(task)
            with patch('runner.mock_output', side_effect=one_failure):
                job = manager.start({'mode': 'mock', 'conditions': ['baseline', 'positive_social'],
                                     'scenario_ids': [store.design()['scenarios'][0]['id']]})
                for _ in range(100):
                    state = manager.get(job['id'])
                    if state['status'] in ('complete', 'error', 'cancelled'):
                        break
                    time.sleep(.01)
            self.assertEqual(state['status'], 'complete')
            self.assertEqual(state['failed'], 1)
            self.assertEqual(state['completed'], 2)
            self.assertEqual({r['status'] for r in store.trials()}, {'error', 'complete'})

    def test_clean_role_and_blind_coder(self):
        d = initial_design()
        s = d['scenarios'][0]
        fixed = None
        for category in ('negative_social', 'positive_social', 'negative_nonsocial', 'neutral_daily'):
            m = [x for x in d['memories'] if x['category'] == category]
            p = role_messages(d, s, m)
            self.assertEqual(len(p['messages']), 2)
            self.assertEqual(p['messages'][1]['content'].split('现在发生了这样一件事：')[1],
                             role_messages(d, s, [])['messages'][1]['content'].split('现在发生了这样一件事：')[1])
            self.assertNotIn(category, json.dumps(p['messages'], ensure_ascii=False))
            self.assertNotIn('焦虑', json.dumps(p['messages'], ensure_ascii=False))
            if fixed is None:
                fixed = p['messages'][0]
            self.assertEqual(fixed, p['messages'][0])
            e = evaluator_messages(s, '我先等一会儿。', d['coding_rules'])
            for x in m:
                self.assertNotIn(x['text'], json.dumps(e, ensure_ascii=False))
        self.assertEqual(len(plan(d, {'conditions': list(d['conditions']), 'scenario_ids': [s['id']], 'repeats': 1})['tasks']), 5)

    def test_unclear_coding_and_denominator(self):
        validate_coding({'interpretation': 'unclear', 'action': 'other', 'coding_confidence': 0.2, 'coding_reason': '未表态'})
        records = [{'source': 'LIVE_LLM_API', 'status': 'complete', 'condition': 'baseline', 'scenario_id': 'S01',
                    'scenario_kind': 'social', 'machine_coding': {'interpretation': 'unclear', 'action': 'other'}},
                   {'source': 'LIVE_LLM_API', 'status': 'complete', 'condition': 'baseline', 'scenario_id': 'S01',
                    'scenario_kind': 'social', 'machine_coding': {'interpretation': 'negative', 'action': 'avoid'}},
                   {'source': 'MOCK_NOT_LLM', 'status': 'complete', 'condition': 'baseline', 'scenario_id': 'S01',
                    'scenario_kind': 'social', 'machine_coding': {'interpretation': 'negative', 'action': 'avoid'}}]
        x = summarize(records)['by_condition']['baseline']
        self.assertEqual(x['n'], 2)
        self.assertEqual(x['interpretation_n'], 1)
        self.assertEqual(x['negative_rate'], 1)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); cls.port = sock.getsockname()[1]; sock.close()
        env = os.environ.copy(); env['SOS_PILOT_DB'] = str(Path(cls.tmp.name) / 'test.sqlite3')
        cls.proc = subprocess.Popen([sys.executable, str(ROOT / 'server.py'), '--port', str(cls.port)],
                                    cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                cls.get('/api/bootstrap'); break
            except Exception:
                time.sleep(.1)
        else:
            raise RuntimeError('server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate(); cls.proc.wait(timeout=5); cls.tmp.cleanup()

    @classmethod
    def get(cls, path):
        with urllib.request.urlopen(f'http://127.0.0.1:{cls.port}{path}', timeout=4) as r:
            return r.read()

    @classmethod
    def post(cls, path, payload):
        req = urllib.request.Request(f'http://127.0.0.1:{cls.port}{path}',
            data=json.dumps(payload, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=4) as r:
            return json.load(r)

    def test_end_to_end_mock_save_edit_export(self):
        d = json.loads(self.get('/api/bootstrap'))['design']
        self.assertEqual(len(d['memories']), 10)
        self.assertGreaterEqual(sum(s['kind']=='social' for s in d['scenarios']), 6)
        self.assertGreaterEqual(sum(s['kind']=='non_social' for s in d['scenarios']), 2)
        d['memories'][0]['text'] = '我参加讨论时，提出一个想法，大家没有接话。'
        self.post('/api/design', d)
        self.assertEqual(json.loads(self.get('/api/bootstrap'))['design']['memories'][0]['text'], d['memories'][0]['text'])
        ids = [s['id'] for s in d['scenarios'][:1]]
        p0 = self.post('/api/preview', {'scenario_id': ids[0], 'condition': 'baseline'})
        p1 = self.post('/api/preview', {'scenario_id': ids[0], 'condition': 'negative_social'})
        self.assertEqual(p0['messages'][0], p1['messages'][0])
        self.assertEqual(len(p0['messages']), 2)
        self.assertNotIn('negative_social', json.dumps(p1['messages']))
        job = self.post('/api/jobs', {'mode': 'mock', 'model': 'mock-test', 'conditions': list(d['conditions']),
                                      'scenario_ids': ids, 'repeats': 2})
        for _ in range(100):
            state = json.loads(self.get('/api/jobs/' + job['id']))
            if state['status'] in ('complete', 'error', 'cancelled'): break
            time.sleep(.05)
        self.assertEqual(state['status'], 'complete')
        rows = json.loads(self.get('/api/trials'))
        self.assertEqual(len(rows), 10)
        self.assertEqual({r['condition'] for r in rows}, set(d['conditions']))
        self.assertTrue(all(r['snapshot'] and r['role_messages'] and r['evaluator_messages'] for r in rows))
        self.assertTrue(all(r['source'] == 'MOCK_NOT_LLM' for r in rows))
        analysis = self.post('/api/analysis', {'source': 'MOCK_NOT_LLM'})
        self.assertEqual(analysis['n'], 10)
        self.assertEqual(analysis['by_condition']['baseline']['n'], 2)
        exported = list(csv.DictReader(io.StringIO(self.get('/api/export.csv').decode('utf-8-sig'))))
        self.assertEqual(len(exported), 10)
        self.assertTrue(all(r['source'] == 'MOCK_NOT_LLM' for r in exported))
        self.assertEqual(len(json.loads(self.get('/api/export.json'))['records']), 10)
        self.assertGreater(len(self.get('/')), 1000)
        self.assertGreater(len(self.get('/app.js')), 1000)
        self.assertGreater(len(self.get('/style.css')), 1000)
        reviewed = self.post('/api/trials/' + rows[0]['id'] + '/review', {'coding': {'interpretation':'unclear',
            'action':'other','coding_confidence':1,'coding_reason':'人工复核'}, 'note':'测试'})
        self.assertEqual(reviewed['human_review']['coding']['interpretation'], 'unclear')
        self.assertIsNotNone(reviewed['machine_coding'])
        human = self.post('/api/human/import', {'csv': 'participant_id,anxiety_score,scenario_id,interpretation,action\nP1,27,S01,neutral,wait\n'})
        self.assertEqual(human['human_count'], 1)
        preview = self.post('/api/preview', {'scenario_id': ids[0], 'condition': 'baseline'})
        self.assertNotIn('27', json.dumps(preview['messages'], ensure_ascii=False))

    def test_five_model_batch_and_legacy_records(self):
        d = json.loads(self.get('/api/bootstrap'))['design']
        before = json.loads(self.get('/api/trials'))
        models = [{'provider': p, 'model': info['model']} for p, info in PROVIDERS.items()]
        job = self.post('/api/jobs', {'mode':'mock', 'models': models,
            'evaluator':{'provider':'openai','model':'gpt-6-luna'},
            'conditions':list(d['conditions']), 'scenario_ids':[d['scenarios'][0]['id']],
            'repeats':1, 'max_calls':25, 'concurrency':2})
        for _ in range(100):
            state = json.loads(self.get('/api/jobs/' + job['id']))
            if state['status'] in ('complete','error','cancelled'): break
            time.sleep(.05)
        self.assertEqual(state['status'],'complete')
        rows = json.loads(self.get('/api/trials'))
        self.assertEqual(len(rows),len(before)+25)
        self.assertEqual({r['provider'] for r in rows if r['batch_id']==job['id']},set(PROVIDERS))
        self.assertTrue(all(r['evaluator_provider']=='openai' and r['evaluator_model']=='gpt-6-luna'
            for r in rows if r['batch_id']==job['id']))
        sample = [r for r in rows if r['batch_id']==job['id'] and r['condition']=='baseline']
        self.assertEqual(len({json.dumps(r['role_messages'], ensure_ascii=False) for r in sample}),1)
        self.assertTrue(all(r['provider'] not in json.dumps(r['evaluator_messages'], ensure_ascii=False)
            for r in rows if r['batch_id']==job['id']))
        report = self.post('/api/model-analysis', {'source':'MOCK_NOT_LLM','filters':{'batch_id':job['id']}})
        self.assertEqual(report['n'],25)
        self.assertEqual(len(report['models']),5)
        self.assertTrue(all(x['by_condition']['baseline']['n']==1 for x in report['models']))
        self.assertEqual(json.loads(self.get('/api/export.json'))['records'][:len(before)],before)

    def test_state_demo_api_and_separate_exports(self):
        protocol = json.loads(self.get('/api/state/bootstrap'))['protocol']
        old_count = len(json.loads(self.get('/api/trials')))
        payload = {'protocol': protocol['protocol'], 'mode': 'mock', 'scenario_ids': ['S01'], 'repeats': 1}
        estimate = self.post('/api/estimate', payload)
        self.assertEqual(estimate['role_calls'], 3)
        preview = self.post('/api/state/preview', {**payload, 'conditions': ['state_mild']})
        self.assertNotIn('state_mild', json.dumps(preview['messages']))
        job = self.post('/api/jobs', payload)
        for _ in range(100):
            state = json.loads(self.get('/api/jobs/' + job['id']))
            if state['status'] in ('complete', 'error', 'cancelled'):
                break
            time.sleep(.03)
        self.assertEqual(state['status'], 'complete')
        report = self.post('/api/state/report', {'source': 'MOCK_NOT_LLM', 'filters': {'batch_id': job['id']}})
        self.assertEqual(report['n'], 3)
        self.assertEqual(len(json.loads(self.get('/api/trials'))), old_count)
        self.assertEqual(len(json.loads(self.get('/api/state/export.json'))['records']), 3)
        exported = list(csv.DictReader(io.StringIO(self.get('/api/state/export.csv').decode('utf-8-sig'))))
        self.assertEqual({r['target_state'] for r in exported}, {'none', 'mild', 'moderate'})
        self.assertEqual(len(self.get('/api/state/human-template.csv').decode('utf-8-sig').splitlines()), 1)
        self.assertGreater(len(self.get('/study.js')), 1000)
        self.assertGreater(len(self.get('/study.css')), 1000)
        self.assertGreater(len(self.get('/workbench')), 1000)


if __name__ == '__main__': unittest.main()
