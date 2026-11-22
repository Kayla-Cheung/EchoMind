import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_client import PROVIDERS, build_request, call, endpoint, extract_final, make_spec, provider_info
from design import initial_design
from runner import plan


class AdapterTests(unittest.TestCase):
    def test_five_official_endpoints_and_final_only(self):
        for provider, d in PROVIDERS.items():
            with self.subTest(provider=provider):
                spec = make_spec({'provider': provider, 'model': d['model']})
                url = endpoint(spec)
                self.assertTrue(url.startswith(d['base']))
                self.assertTrue(url.endswith('/responses' if provider == 'openai' else '/chat/completions'))
                response = ({'id':'r1','model':spec.model,'status':'completed','output':[{'type':'reasoning','summary':[]},
                    {'type':'message','content':[{'type':'output_text','text':'我再等等。'}]}], 'usage':{'input_tokens':4,'output_tokens':7}}
                    if provider == 'openai' else {'id':'r1','model':spec.model,'choices':[{'finish_reason':'stop',
                    'message':{'reasoning_content':'内部推理不得进入结果','content':'<think>隐藏内容</think>我再等等。'}}],
                    'usage':{'prompt_tokens':4,'completion_tokens':7}})
                def transport(target, body, timeout):
                    self.assertEqual(target, url)
                    self.assertEqual(body['model'], spec.model)
                    self.assertEqual(len(body.get('messages',body.get('input'))), 2)
                    return response
                final, meta = call(spec, [{'role':'system','content':'身份'}, {'role':'user','content':'事件'}], transport=transport)
                self.assertEqual(final, '我再等等。')
                self.assertNotIn('内部推理', final)
                self.assertEqual(meta['response_model'], spec.model)
                self.assertIn('latency_ms', meta)

    def test_capabilities_and_china_region(self):
        mini = make_spec({'provider':'minimax','model':'MiniMax-M3.1-Flash','region':'china','reasoning_effort':'low'})
        self.assertEqual(endpoint(mini), 'https://api.minimaxi.com/v1/chat/completions')
        self.assertEqual(build_request(mini,[{'role':'user','content':'x'}])['reasoning_split'], True)
        self.assertRaises(ValueError, make_spec, {'provider':'minimax','model':'MiniMax-M3.1-Flash','thinking':'disabled'})
        self.assertRaises(ValueError, make_spec, {'provider':'mimo','model':'mimo-v2.6-flash','temperature':0.7})
        self.assertRaises(ValueError, make_spec, {'provider':'deepseek','model':'deepseek-flash','temperature':0.7})
        d = make_spec({'provider':'deepseek','model':'deepseek-flash','thinking':'disabled','temperature':0.7})
        self.assertEqual(build_request(d,[{'role':'user','content':'x'}])['temperature'],0.7)
        self.assertIn('max_tokens',build_request(d,[{'role':'user','content':'x'}]))
        self.assertRaises(ValueError,make_spec,{'provider':'openai','model':'gpt-6-luna','temperature':0.7})
        self.assertRaises(ValueError,make_spec,{'provider':'gemini','model':'gemini-3.8-flash','temperature':0.7})
        self.assertRaises(RuntimeError,extract_final,mini,{'choices':[{'message':{'reasoning_content':'only','content':''}}]})

    def test_five_model_plan_fixed_evaluator_and_limit(self):
        d=initial_design()
        models=[{'provider':p,'model':v['model']} for p,v in PROVIDERS.items()]
        request={'mode':'mock','models':models,'evaluator':{'provider':'openai','model':'gpt-6-luna'},
                 'conditions':list(d['conditions']),'scenario_ids':[d['scenarios'][0]['id']],
                 'repeats':1,'max_calls':25,'concurrency':2}
        p=plan(d,request)
        self.assertEqual(p['calls'],25)
        self.assertEqual(p['coding_calls'],0)
        self.assertEqual({t['model_spec'].provider for t in p['tasks']},set(PROVIDERS))
        self.assertEqual(p['evaluator'].provider,'openai')
        request['max_calls']=24
        self.assertRaises(ValueError,plan,d,request)

    def test_key_not_exposed_in_status(self):
        old=os.environ.get('DEEPSEEK_API_KEY')
        os.environ['DEEPSEEK_API_KEY']='secret-test-marker'
        try:
            info=json.dumps(provider_info())
            self.assertNotIn('secret-test-marker',info)
            self.assertIn('DEEPSEEK_API_KEY',info)
        finally:
            if old is None: os.environ.pop('DEEPSEEK_API_KEY',None)
            else: os.environ['DEEPSEEK_API_KEY']=old

if __name__=='__main__': unittest.main()
