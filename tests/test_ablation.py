import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ablation import (PROTOCOL_ID, CODER_VERSION, MEMORY_GROUPS, FORMATS,
                      summarize_ablation)
from design import initial_design
from prompts import role_messages, evaluator_messages
from runner import plan, execute_task, JobManager
from storage import Store


def request(n=2):
    return {'protocol':PROTOCOL_ID, 'mode':'mock', 'repeats':n,
            'models':[{'provider':'deepseek','model':'deepseek-flash','thinking':'disabled','temperature':1}],
            'evaluator':{'provider':'deepseek','model':'deepseek-flash','thinking':'disabled','temperature':0},
            'scenario_ids':['S01'], 'variants':['A'], 'conditions':list(MEMORY_GROUPS),
            'formats':list(FORMATS), 'max_calls':800}


class AblationLogic(unittest.TestCase):
    def test_factorial_count_and_separation(self):
        settings=plan(initial_design(), request(3))
        self.assertEqual(settings['calls'],24)
        self.assertEqual(len({(t['condition'], t['ablation_format']) for t in settings['tasks']}),8)
        self.assertEqual(len({(t['condition'],t['ablation_format'],t['repeat']) for t in settings['tasks']}),24)
        self.assertEqual(len({t['scenario']['id'] for t in settings['tasks']}),1)
        self.assertEqual(len({t['model_spec'].model for t in settings['tasks']}),1)
        for changes in ({'formats':['free']},{'conditions':['positive_self','negative_self']},
                        {'variants':['A','B']},{'scenario_ids':['S01','S03']},
                        {'repeats':101}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                plan(initial_design(), {**request(3),**changes})

    def test_prompt_attribution_and_format_only(self):
        d=initial_design(); tasks=plan(d,request(1))['tasks']
        prompts={}
        for t in tasks:
            p=role_messages(d,t['scenario'],t['memories'],output_mode=t['ablation_format'],memory_source=t['memory_source'])
            prompts[(t['ablation_format'],t['condition'])]=p
            self.assertNotIn('目标中度',str(p))
            self.assertNotIn('negative_self',str(p))
            self.assertNotIn('anxiety',str(p))
        for fmt in FORMATS:
            own=prompts[(fmt,'negative_self')]['messages'][1]['content']
            other=prompts[(fmt,'negative_other')]['messages'][1]['content']
            blank=prompts[(fmt,'baseline')]['messages'][1]['content']
            self.assertIn('你记得的一些往事',own)
            self.assertIn('不是你的经历',other)
            self.assertIn('他讲了自己的方案',other)
            self.assertNotIn('你记得的一些往事',blank)
            self.assertNotIn('不是你的经历',blank)
        self.assertIn('内心想法',prompts[('channels','negative_self')]['messages'][1]['content'])
        self.assertIn('连续叙述',prompts[('free','negative_self')]['messages'][1]['content'])
        self.assertEqual({p['messages'][0]['content'].split('本次以用户')[0].rstrip() for p in prompts.values()},
                         {prompts[('free','negative_self')]['messages'][0]['content']})

    def test_coder_blind_and_explicit_rules(self):
        d=initial_design();scene=d['scenarios'][0]
        for fmt in FORMATS:
            p=evaluator_messages(scene,'又是已读不回，我犹豫了一下。',d['coding_rules'],ablation_format=fmt)
            c=json.dumps(p,ensure_ascii=False)
            self.assertIn('又是已读不回',c)
            self.assertNotIn('negative_self',c)
            self.assertEqual(p['coder_version'],CODER_VERSION)

    def test_mock_batch_and_never_claims_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            st=Store(Path(temp)/'temp.sqlite3');m=JobManager(st)
            j=m.start(request(3))
            for _ in range(500):
                last=m.get(j['id'])
                if last['status'] in ('complete','error','cancelled'): break
                time.sleep(.01)
            self.assertEqual(last['completed'],24)
            self.assertEqual(last['failed'],0)
            rows=st.trials()
            self.assertEqual(len(rows),24)
            self.assertTrue(all(r['status']=='complete' for r in rows))
            self.assertTrue(all(r['coder_version']==CODER_VERSION for r in rows))
            self.assertTrue(all(r.get('channels') is None for r in rows if r['ablation_format']=='free'))
            self.assertTrue(all(r.get('channels') is not None for r in rows if r['ablation_format']=='channels'))
            report=summarize_ablation(rows,j['id'])
            self.assertEqual(report['status'],'mock')
            self.assertEqual(report['complete_n'],24)
            self.assertFalse(report['blockers'])
            self.assertEqual(report['format_interaction_descriptive'],0)
            self.assertEqual(set(r['protocol'] for r in rows),{PROTOCOL_ID})

    def test_free_text_runs_without_format_parser(self):
        with tempfile.TemporaryDirectory() as temp:
            st=Store(Path(temp)/'temp.sqlite3')
            settings=plan(st.design(),{**request(1),'mode':'live'})
            task=next(t for t in settings['tasks'] if t['ablation_format']=='free')
            coding=json.dumps({'interpretation':'unclear','action':'other','coding_confidence':.6,'coding_reason':'没有清晰归因'})
            with patch('runner.call',side_effect=[('我不知道对方为什么还没回。',{}),(coding,{})]):
                row=execute_task(st,st.design(),task,settings,'test', __import__('threading').Event())
            self.assertEqual(row['status'],'complete')
            self.assertNotIn('channels',row)
            self.assertEqual(row['machine_coding']['interpretation'],'unclear')

    def test_old_database_untouched_and_evidence_is_new_protocol(self):
        with tempfile.TemporaryDirectory() as temp:
            st=Store(Path(temp)/'temp.sqlite3')
            st.add_trial({'id':'old','timestamp':'2026-01-01T00:00:00Z','batch_id':'old',
                          'source':'MOCK_NOT_LLM','status':'complete','protocol':'memory-ratio-v1'})
            JobManager(st).start(request(1))
            time.sleep(.3)
            self.assertTrue(any(r['id']=='old' and r['protocol']=='memory-ratio-v1' for r in Store(st.path).trials()))


class AblationHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(); sock=socket.socket();sock.bind(('127.0.0.1',0));cls.port=sock.getsockname()[1];sock.close()
        env=os.environ.copy();env['SOS_PILOT_DB']=str(Path(cls.temp.name)/'temp.sqlite3')
        cls.server=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--port',str(cls.port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:cls.get('/api/ablation/bootstrap');break
            except Exception:time.sleep(.1)
        else:raise RuntimeError('server failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate();cls.server.wait(timeout=5);cls.temp.cleanup()

    @classmethod
    def get(cls,path):
        with urllib.request.urlopen(f'http://127.0.0.1:{cls.port}{path}', timeout=4) as response:return response.read(),response.headers.get('Content-Type')

    @classmethod
    def post(cls,path,data):
        req=urllib.request.Request(f'http://127.0.0.1:{cls.port}{path}',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)

    def test_browser_assets_and_mock_api(self):
        for url, mime in (('/ablation','text/html'),('/ablation.js','application/javascript'),('/ablation.css','text/css'),('/ablation-protocol.md','text/plain')):
            raw, content_type=self.get(url)
            self.assertTrue(raw)
            self.assertTrue(content_type.startswith(mime))
        boot=json.loads(self.get('/api/ablation/bootstrap')[0]);self.assertEqual(boot['protocol'],PROTOCOL_ID)
        req=request(1)
        self.assertEqual(self.post('/api/estimate',req)['role_calls'],8)
        preview=self.post('/api/ablation/preview',{**req,'preview_condition':'negative_other','preview_format':'free'})
        self.assertIn('不是你的经历',str(preview))
        job=self.post('/api/jobs',req)
        for _ in range(300):
            status=json.loads(self.get('/api/jobs/'+job['id'])[0])
            if status['status']=='complete':break
            time.sleep(.01)
        self.assertEqual(status['completed'],8)
        report=self.post('/api/ablation/report',{'batch_id':job['id']})
        self.assertEqual(report['status'],'mock')
        self.assertEqual(report['complete_n'],8)
        self.assertEqual(len(report['records']),8)
        self.assertIn(b'ablation_format',self.get('/api/ablation/export.csv?batch_id='+job['id'])[0])
        self.assertEqual(json.loads(self.get('/api/ablation/export.json?batch_id='+job['id'])[0])['status'],'mock')

if __name__=='__main__':unittest.main()
