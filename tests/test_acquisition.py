"""Controlled v0.2 tests. All databases temporary; all LIVE-shaped calls are fakes."""
import copy
import csv
import io
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from echomind import acquisition as a
from echomind.history import digest, batch_report, export, import_records
from echomind.model_client import call, build_request, make_spec, ProviderError
from echomind.runner import JobManager, plan
from echomind.storage import Store


def prepared(store, **extra):
    request = {"protocol": a.PROTOCOL_ID, "mode": "mock", **extra}
    settings = plan(store.design(), request)
    request["preview_hash"] = settings["preview_hash"]
    return request, settings


def finish(manager, request):
    job = manager.start(request)
    for _ in range(2000):
        saved = manager.get(job["id"])
        if saved["status"] not in ("queued", "running"):
            return saved
        time.sleep(.02)
    raise AssertionError("MVP did not finish")


def fake_caller(spec, messages, *, evaluator=False, audit, **kwargs):
    body = build_request(spec, messages, evaluator=evaluator)
    audit({"event": "request", "attempt": 1, "body": body, "endpoint": "FAKE_TEST_TRANSPORT"})
    response, coding = a.mock_decision(1)
    text = json.dumps(coding if evaluator else response, ensure_ascii=False) if evaluator or 'JSON' in messages[-1]['content'] else '收到。'
    meta = {"usage": {"prompt_tokens": 100, "completion_tokens": 30, "prompt_tokens_details": {"cached_tokens": 0}},
            "response_model": spec.model, "system_fingerprint": "TEST_ONLY", "attempts": 1,
            "sent_parameters": {k: v for k, v in body.items() if k not in ('messages', 'input')}}
    audit({"event": "response", "attempt": 1, "public_response": text, "meta": meta})
    return text, meta


class AcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / 'original.sqlite3'
        cls.store = Store(cls.path)
        cls.old = {"id": "old-before-v02", "timestamp": "2026-10-20T10:00:00+00:00", "batch_id": "old",
                   "source": "LIVE_LLM_API", "status": "error", "protocol": "memory-ratio-v1", "error": "historical 401"}
        cls.store.add_trial(cls.old)
        cls.request, cls.settings = prepared(cls.store)
        cls.job = finish(JobManager(cls.store), cls.request)
        assert cls.job['status'] == 'complete', cls.job
        cls.report = a.export_batch(cls.store, cls.job['id'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def cloned(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'copy.sqlite3'
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(path)) as target:
            source.backup(target)
        return Store(path)

    def test_default_counts_and_zero_real_requests(self):
        self.assertEqual((self.job['total'], self.job['completed'], self.job['failed']), (84,84,0))
        self.assertEqual((self.job['api_attempts'], self.job['simulated_attempts']), (0,180))
        self.assertEqual(len(self.report['snapshots']), 21)
        self.assertEqual(len(self.report['call_events']), 360)
        self.assertEqual(set(r['condition_id'] for r in self.report['records']), set(a.CONDITIONS))
        preview = a.preview(self.settings)
        self.assertEqual((preview['calls'],preview['acquisition_calls'],preview['coding_calls']), (84,12,84))
        _, smoke = prepared(self.store, phase='smoke_test')
        self.assertEqual((smoke['calls'],smoke['nominal_api_calls']), (28,60))

    def test_canonical_fact_coverage_and_no_scheduling_labels(self):
        for event in a.EVENTS.values():
            for method in a.METHODS:
                messages=a.memory_messages(event,method)
                text='\n'.join(m['content'] for m in messages)
                for unit in a.fact_units(event):self.assertEqual(text.count(unit['rendered']),1)
                a.reject_labels(messages)
                self.assertNotIn('valence_label',text)
                self.assertNotIn(event['event_id'],text)
        self.assertEqual(a.EVENTS['neutral']['event_sequence'],a.EVENTS['negative']['event_sequence'])
        self.assertEqual(a.EVENTS['neutral']['participants'],a.EVENTS['negative']['participants'])

    def test_three_independent_interactive_acquisitions_per_content(self):
        for condition in ['neutral_interactive','negative_interactive']:
            snaps=[s for s in self.report['snapshots'] if s['condition_id']==condition]
            self.assertEqual(len(snaps),3)
            self.assertEqual(len({s['id'] for s in snaps}),3)
            for snap in snaps:
                self.assertEqual(len(snap['intermediate']),2)
                self.assertEqual([m['role'] for m in snap['messages']],['system','user','assistant','user','assistant'])
                self.assertEqual(snap['intermediate'][1]['messages_before'],snap['messages'][:-1])
                self.assertTrue(all(step['response']=='我听到了。' for step in snap['intermediate']))

    def test_immutable_snapshots_and_four_isolated_branches(self):
        store=self.cloned()
        for snap in self.report['snapshots']:
            children=[r for r in self.report['records'] if r['memory_snapshot_id']==snap['id']]
            self.assertEqual(len(children),4)
            self.assertEqual({r['scenario_id'] for r in children},{s['scenario_id'] for s in a.SCENARIOS})
            self.assertTrue(all(r['role_messages'][:-1]==snap['messages'] for r in children))
            copy_snap=store.memory_snapshot(snap['id']);copy_snap['messages'].append({'role':'user','content':'pollution'})
            self.assertEqual(store.memory_snapshot(snap['id']),snap)
            with self.assertRaises(ValueError):store.freeze_memory(copy_snap)
        with self.assertRaises(sqlite3.IntegrityError), store.connection() as db:
            db.execute("UPDATE acquisition_snapshots SET payload='{}'")
        for event in self.report['call_events']:
            if event['event']=='request':
                self.assertFalse(any(k in event['body'] for k in ['conversation','previous_response_id','session_id']))

    def test_blind_coder_has_only_public_fields_and_fixed_rules(self):
        for row in self.report['records']:
            expected=a.coder_messages(row['scenario'],row['agent_parsed'],self.settings['config']['coding_rules'])
            self.assertEqual(row['evaluator_messages'],expected)
            a.reject_labels(expected)
            text=json.dumps(expected,ensure_ascii=False)
            self.assertNotIn('陈晨',text)
            self.assertNotIn('event_id',text)
            self.assertIn(row['agent_parsed']['interpretation'],text)
        parsed={'interpretation':'我想到上周陈晨说的话。','speech':'','action':'我先等候。'}
        self.assertIn('陈晨',json.dumps(a.coder_messages(a.SCENARIOS[0],parsed,'固定规则'),ensure_ascii=False))

    def test_recalculate_and_export_without_mutating_old_records(self):
        reopened=Store(self.path)
        self.assertEqual(a.export_batch(reopened,self.job['id'])['strata'],self.report['strata'])
        self.assertEqual(next(r for r in reopened.trials() if r['id']==self.old['id']),self.old)
        before=list((self.path.parent/'backups').glob('*.sqlite3'))
        reopened.ensure_acquisition_schema()
        self.assertEqual(list((self.path.parent/'backups').glob('*.sqlite3')),before)
        with closing(sqlite3.connect(before[0])) as db:
            self.assertEqual(json.loads(db.execute('SELECT payload FROM trials').fetchone()[0]),self.old)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='acquisition_snapshots'").fetchone())
        csvrows=list(csv.DictReader(io.StringIO(a.export_csv(self.report).lstrip('\ufeff'))))
        self.assertEqual(sum(r['row_type']=='decision' for r in csvrows),84)
        self.assertEqual(sum(r['row_type']=='memory_snapshot' for r in csvrows),21)
        self.assertEqual(sum(r['row_type']=='call_event' for r in csvrows),360)
        first=next(r for r in csvrows if r['row_type']=='decision')
        self.assertEqual(json.loads(first['payload_json']),self.report['records'][0])

    def test_analysis_separates_scenarios_phases_and_versions(self):
        self.assertEqual(len(self.report['strata'][0]['scenarios']),4)
        for scene in self.report['strata'][0]['scenarios']:
            for cell in scene['cells']:
                self.assertEqual(cell['coded_n'],3)
                self.assertEqual(cell['counts']['interpretation']['negative'],1)
            for effects in scene['memory_effects'].values():
                self.assertTrue(all(v==0 for axis in effects.values() for v in axis.values()))
        rows=copy.deepcopy(self.report['records'])
        rows[0]['phase']='smoke_test'
        report=a.summarize(rows,self.job['id'])
        self.assertEqual(len(report['strata']),2)
        rows=copy.deepcopy(self.report['records']);rows[0]['role_meta']['response_model']='changed-version'
        self.assertEqual(len(a.summarize(rows,self.job['id'])['strata']),2)
        old=copy.deepcopy(self.old);old['batch_id']=self.job['id']
        self.assertEqual(a.summarize(self.report['records']+[old],self.job['id'])['recorded'],84)
        self.assertIn('acquisition_report',batch_report(self.store.trials(),self.job['id']))

    def test_uncoded_and_missing_samples_do_not_become_negative_absence(self):
        rows=copy.deepcopy(self.report['records']);bad=rows[0];bad.update(status='error',machine_coding=None)
        report=a.summarize(rows,self.job['id'])
        scene=next(s for t in report['strata'] for s in t['scenarios'] if s['scenario']['scenario_id']==bad['scenario_id'])
        cell=next(c for c in scene['cells'] if c['condition']==bad['condition'])
        self.assertEqual((cell['coded_n'],cell['failed_or_uncoded']),(2,1))
        if bad['acquisition_method']!='none':self.assertIsNone(scene['memory_effects'][bad['acquisition_method']])

    def test_preview_gate_and_unsupported_sampling_rejected_before_writes(self):
        store=self.cloned();count=len(store.trials());manager=JobManager(store)
        with self.assertRaises(ValueError):manager.start({'protocol':a.PROTOCOL_ID,'mode':'mock'})
        req,_=prepared(store);req['repeats']=2
        with self.assertRaises(ValueError):manager.start(req)
        for value in [{'models':[{'provider':'openai','model':'gpt-6-luna'}]},
                      {'models':[{'provider':'deepseek','seed':1}]},{'max_api_calls':1}]:
            with self.assertRaises(ValueError):prepared(store,**value)
        self.assertEqual(len(store.trials()),count)

    def test_real_requires_keys_explicit_confirmation_and_mock_gate(self):
        rates={'currency':'TEST','agent':{'input_per_million':1,'output_per_million':1},'coder':{'input_per_million':1,'output_per_million':1}}
        req,settings=prepared(self.store,mode='live',phase='smoke_test',pricing=rates,max_cost=10)
        with self.assertRaises(ValueError):a.check_start(self.store,settings)
        req,settings=prepared(self.store,mode='live',phase='smoke_test',pricing=rates,max_cost=10,confirm_live=True)
        settings['request_snapshot']['preview_hash']=req['preview_hash']
        with patch('echomind.acquisition.provider_info',return_value=[{'id':'deepseek','configured':False}]), patch('echomind.runner.call') as network:
            with self.assertRaises(ValueError):a.check_start(self.store,settings)
            network.assert_not_called()
        with patch('echomind.runner.offline_mode',return_value=True):
            with self.assertRaises(ValueError):JobManager(self.store).start(req)

    def test_fake_transport_gate3_is_required_and_bound_to_28_smoke_records(self):
        store=self.cloned()
        rates={'currency':'TEST','agent':{'input_per_million':1,'output_per_million':1},'coder':{'input_per_million':1,'output_per_million':1}}
        common={'mode':'live','pricing':rates,'max_cost':10,'confirm_live':True}
        with patch('echomind.runner.offline_mode',return_value=False), patch('echomind.acquisition.provider_info',return_value=[{'id':'deepseek','configured':True}]), patch('echomind.runner.call',side_effect=fake_caller):
            req,_=prepared(store,**common)
            with self.assertRaises(ValueError):JobManager(store).start(req)
            req,_=prepared(store,phase='smoke_test',mock_batch_id=self.job['id'],**common)
            job=finish(JobManager(store),req)
            self.assertEqual((job['status'],job['completed'],job['api_attempts']),('complete',28,60))
            gate=a.review_smoke(store,{'batch_id':job['id'],'reviewer':'TEST ONLY','notes':'synthetic transport fixture, not real provider evidence','checks':dict.fromkeys(a.GATE_CHECKS,True)})
            req,settings=prepared(store,smoke_batch_id=job['id'],**common)
            settings['request_snapshot']['preview_hash']=req['preview_hash']
            a.check_start(store,settings)
            self.assertEqual(gate['records_hash'],digest([r for r in store.trials() if r.get('batch_id')==job['id']]))
            self.assertEqual(gate['audit_hash'], digest(store.acquisition_rows('acquisition_call_events', job['id'])))
            saved_setting = store.setting
            def stale_gate(key, default=None):
                value = saved_setting(key, default)
                if key == 'acquisition-gate3:' + job['id']:
                    value.pop('audit_hash')
                return value
            with patch.object(store, 'setting', side_effect=stale_gate):
                with self.assertRaises(ValueError):
                    a.check_start(store,settings)
            saved_rows = store.acquisition_rows
            def appended_snapshot(table, batch_id=None):
                values = saved_rows(table, batch_id)
                return values + [{'id': 'unreviewed'}] if table == 'acquisition_snapshots' else values
            with patch.object(store, 'acquisition_rows', side_effect=appended_snapshot):
                with self.assertRaises(ValueError):
                    a.check_start(store,settings)
            req,settings=prepared(store,smoke_batch_id=job['id'],models=[{'provider':'minimax','model':'MiniMax-M3.1-Flash'}],**common)
            settings['request_snapshot']['preview_hash']=req['preview_hash']
            with self.assertRaises(ValueError):a.check_start(store,settings)

    def test_mutable_copy_cannot_change_protocol_fact_source(self):
        _,settings=prepared(self.store)
        settings['config']['events']['negative']['observable_facts'][0]['text']='changed'
        self.assertNotEqual(settings['config']['events'],a.EVENTS)
        _,fresh=prepared(self.store)
        self.assertEqual(fresh['config']['events'],a.EVENTS)

    def test_gate_rejects_missing_requests_changed_outputs_and_parameters(self):
        store = self.cloned()
        events = store.acquisition_rows('acquisition_call_events', self.job['id'])
        rows = [r for r in store.trials() if r.get('batch_id') == self.job['id']]
        for corruption in ('missing_request', 'extra_request', 'output', 'parameter'):
            altered = copy.deepcopy(events)
            if corruption == 'missing_request':
                altered.pop(0)
            elif corruption == 'extra_request':
                altered.append(copy.deepcopy(altered[0]))
            elif corruption == 'output':
                next(e for e in altered if e['event'] == 'response')['public_response'] = 'changed'
            else:
                next(e for e in altered if e['event'] == 'request')['body']['max_tokens'] = 99999
            with self.subTest(corruption=corruption), patch.object(store, 'acquisition_rows', return_value=altered):
                with self.assertRaises(ValueError):
                    a._validate_batch_audit(store, self.job['id'], rows, self.job)

    def test_real_rejects_zero_rates_before_any_request(self):
        rates = {'currency': 'TEST', 'agent': {'input_per_million': 0, 'output_per_million': 0},
                 'coder': {'input_per_million': 1, 'output_per_million': 1}}
        with patch('echomind.runner.call') as network:
            with self.assertRaises(ValueError):
                prepared(self.store, mode='live', pricing=rates, max_cost=10)
            network.assert_not_called()

    def test_gate_rejects_saved_fields_that_disagree_with_raw_output(self):
        for field, key, value in (('agent_parsed', 'interpretation', 'changed'),
                                  ('machine_coding', 'action', 'avoid')):
            store = self.cloned()
            row = next(r for r in store.trials() if r.get('batch_id') == self.job['id'])
            row[field][key] = value
            store.update_trial(row)
            with self.subTest(field=field), self.assertRaises(ValueError):
                a._complete_rows(store, self.job['id'], self.settings['protocol_hash'],
                                 'MOCK_NOT_LLM', 'exploratory_mvp', 3)

    def fake_job(self, store, suffix):
        return {'id':'TEST-'+suffix,'source':'LIVE_LLM_API','cancel_event':threading.Event(),
                'error':None,'snapshot_ids':[],'record_ids':[],'completed':0,'failed':0,'unissued':84,
                'api_attempts':0,'request_attempts':0,'simulated_attempts':0,'execution_counter':0,
                'cost_accounted':0.0,'cost_from_reported_usage':0.0}

    def live_settings(self, store):
        rates={'currency':'TEST','agent':{'input_per_million':1,'output_per_million':1},'coder':{'input_per_million':1,'output_per_million':1}}
        return prepared(store,mode='live',pricing=rates,max_cost=10)[1]

    def test_budget_cancellation_and_missing_usage_stop_before_next_request(self):
        store=self.cloned();settings=self.live_settings(store);settings['max_cost']=.000001
        job=self.fake_job(store,'budget');budget=a.CallBudget(store,job,settings,lambda j:None)
        with self.assertRaises(ProviderError):budget.invoke(fake_caller,settings['models'][0],[{'role':'user','content':'公开文本'}],'acquisition','s')
        self.assertEqual(job['api_attempts'],0)
        settings['max_cost']=10;job['cancel_event'].set()
        with self.assertRaises(ProviderError):budget.invoke(fake_caller,settings['models'][0],[{'role':'user','content':'公开文本'}],'acquisition','s')
        self.assertEqual(job['api_attempts'],0)
        job['cancel_event'].clear()
        def missing_usage(spec,messages,audit,**kw):
            audit({'event':'request','attempt':1,'body':build_request(spec,messages)})
            meta={'usage':{},'response_model':spec.model}
            audit({'event':'response','attempt':1,'public_response':'收到','meta':meta})
            return '收到',meta
        budget.invoke(missing_usage,settings['models'][0],[{'role':'user','content':'公开文本'}],'acquisition','s')
        with self.assertRaises(ProviderError):budget.invoke(fake_caller,settings['models'][0],[{'role':'user','content':'后续'}],'acquisition','s')
        self.assertEqual(job['api_attempts'],1)

    def test_failed_acquisition_preserves_partial_history_and_stops_branches(self):
        store=self.cloned();settings=self.live_settings(store)
        settings['groups']=[next(g for g in settings['groups'] if g['condition']=='negative_interactive')]
        job=self.fake_job(store,'failed-acquisition');seen=[]
        def fail_second(spec,messages,audit,**kw):
            seen.append(messages)
            if len(seen)==1:return fake_caller(spec,messages,audit=audit,**kw)
            audit({'event':'request','attempt':1,'body':build_request(spec,messages)})
            error=ProviderError('TEST auth failure','authentication',401)
            audit({'event':'error','attempt':1,'error':str(error),'error_meta':error.meta})
            raise error
        a.run(store,job,settings,fail_second,lambda j:None)
        self.assertEqual((job['status'],job['completed'],job['unissued']),('error',0,84))
        snapshots=store.acquisition_rows('acquisition_snapshots',job['id'])
        self.assertEqual(len(snapshots),1)
        self.assertEqual(snapshots[0]['status'],'error')
        self.assertEqual(len(snapshots[0]['intermediate']),1)
        self.assertEqual(snapshots[0]['messages'][2]['role'],'assistant')
        self.assertTrue(any(e['event']=='error' for e in store.acquisition_rows('acquisition_call_events',job['id'])))

    def test_parse_failure_stops_batch_and_keeps_raw_reply(self):
        store=self.cloned();settings=self.live_settings(store)
        settings['groups']=[next(g for g in settings['groups'] if g['condition']=='none')]
        job=self.fake_job(store,'parse')
        def malformed(spec,messages,audit,**kw):
            audit({'event':'request','attempt':1,'body':build_request(spec,messages)})
            meta={'usage':{'prompt_tokens':2,'completion_tokens':3},'response_model':spec.model}
            audit({'event':'response','attempt':1,'public_response':'malformed original','meta':meta})
            return 'malformed original',meta
        a.run(store,job,settings,malformed,lambda j:None)
        row=next(r for r in store.trials() if r.get('batch_id')==job['id'])
        self.assertEqual((job['status'],job['failed'],job['api_attempts']),('error',1,1))
        self.assertEqual(row['narrative'],'malformed original')
        self.assertEqual(row['error_meta']['kind'],'parse')


class AdapterAuditTests(unittest.TestCase):
    def test_original_public_whitespace_is_retained(self):
        spec=make_spec({'provider':'deepseek'})
        original='  {"interpretation":"public", "speech":"", "action":"wait"}\n'
        text,meta=call(spec,[{'role':'user','content':'public'}],transport=lambda *args:{'choices':[{'message':{'content':original},'finish_reason':'stop'}]})
        self.assertEqual(meta['raw_public_parts'],[original])
        self.assertEqual(text,original.strip())

    def test_retry_and_auth_errors_are_audited_without_error_body(self):
        spec=make_spec({'provider':'deepseek','thinking':'disabled'})
        trace=[];seen=[]
        def transport(url,body,timeout):
            seen.append(body)
            if len(seen)==1:raise urllib.error.HTTPError(url,429,'rate limited',{},None)
            return {'model':spec.model,'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}],'usage':{'prompt_tokens':2,'completion_tokens':1}}
        with patch('echomind.model_client.time.sleep'):
            _,meta=call(spec,[{'role':'user','content':'public'}],transport=transport,audit=trace.append)
        self.assertEqual([x['event'] for x in trace],['request','error','request','response'])
        self.assertEqual(meta['attempts'],2)
        trace=[]
        def unauthorized(*args):raise urllib.error.HTTPError('https://example.invalid',401,'do not persist me',{},None)
        with self.assertRaises(ProviderError):call(spec,[{'role':'user','content':'public'}],transport=unauthorized,audit=trace.append)
        self.assertEqual([x['event'] for x in trace],['request','error'])
        self.assertNotIn('do not persist me',json.dumps(trace))

    def test_truncated_output_retains_public_text_and_usage(self):
        spec=make_spec({'provider':'deepseek'})
        with self.assertRaises(ProviderError) as error:
            call(spec,[{'role':'user','content':'public'}],transport=lambda *args:{'choices':[{'message':{'content':'unfinished'},'finish_reason':'length'}],'usage':{'prompt_tokens':3,'completion_tokens':8}})
        self.assertEqual(error.exception.meta['public_response'],'unfinished')
        self.assertEqual(error.exception.meta['usage']['completion_tokens'],8)

    def test_parser_rejects_fabricated_or_missing_fields(self):
        for raw in ['free prose','{"interpretation":"x","speech":""}','{"interpretation":"","speech":"","action":"wait"}']:
            with self.assertRaises(ProviderError):a.parse_response(raw)
        with self.assertRaises(ProviderError):a.reject_labels([{'role':'user','content':'negative_interactive'}])


if __name__ == '__main__':unittest.main()
