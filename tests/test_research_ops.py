"""Recovery, provenance and immutable-source workflow checks."""
from contextlib import closing
import json
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest

from analysis import summarize, model_comparison
from data_audit import Audit, digest, handler
from research_ops import reconcile, sha256, init_audit, identifier
from storage import Store


class ResearchOpsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.primary=self.root/'primary.sqlite3';self.backup=self.root/'backup.sqlite3'
        self.record={'id':'one','timestamp':'2026-11-23T00:00:00+00:00','batch_id':'batch',
                     'source':'LIVE_LLM_API','status':'complete','narrative':'response',
                     'condition':'baseline','scenario_id':'s1','scenario_kind':'social',
                     'machine_coding':{'interpretation':'negative','action':'avoid'}}
        for p in (self.primary,self.backup): Store(p).add_trial(self.record)
        failure=dict(self.record,id='failed',status='error')
        Store(self.backup).add_trial(failure)

    def tearDown(self): self.temp.cleanup()

    def test_recovery_preserves_sources_and_failed_rows_with_provenance(self):
        hashes=[sha256(p) for p in (self.primary,self.backup)]
        result=reconcile(self.primary,self.backup,self.root/'derived'/'recovery')
        self.assertEqual(result['union_trials'],2)
        self.assertEqual(result['absent_from_primary'],1)
        self.assertEqual([sha256(p) for p in (self.primary,self.backup)],hashes)
        with closing(sqlite3.connect(self.root/'derived/recovery/reconciled-trials.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM provenance').fetchone()[0],3)
            self.assertEqual(db.execute("SELECT status FROM trials WHERE id='failed'").fetchone()[0],'error')
        with self.assertRaises(ValueError): reconcile(self.primary,self.backup,self.root/'derived'/'recovery')
        audit=Audit(self.root,self.root/'audit-state');r=audit.scan()
        self.assertEqual(r['unique_trial_ids'],2)
        derived=[d for d in r['databases'] if d.get('role')=='derived_recovery']
        self.assertEqual(len(derived),1)

    def test_conflicts_refuse_recovery_before_creating_output(self):
        with closing(sqlite3.connect(self.backup)) as db, db:
            db.execute("UPDATE trials SET payload=? WHERE id='one'",(json.dumps(dict(self.record,narrative='different')),))
        with self.assertRaises(ValueError): reconcile(self.primary,self.backup,self.root/'conflict')
        self.assertFalse((self.root/'conflict').exists())

    def test_legacy_review_preserves_trial_bytes_and_history(self):
        store=Store(self.primary)
        before=sha256(self.primary)
        first=store.review('one',{'interpretation':'neutral','action':'wait'},'first')
        store.review('one',{'interpretation':'negative','action':'avoid'},'second')
        self.assertEqual(sha256(self.primary),before)
        self.assertNotIn('human_review',store.trials()[0])
        with closing(sqlite3.connect(first['review_journal'])) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM review_events').fetchone()[0],2)
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM review_events')

    def test_decision_freeze_preserves_events_and_marks_changed_rows(self):
        audit=Audit(self.root,self.root/'audit-state');r=audit.scan()
        key=next(d['key'] for d in r['databases'] if d['path']=='primary.sqlite3')
        event=dict(db=key,table='trials',rowid=1,row_hash=digest(audit.row(key,'trials',1)),reviewer='coder',decision='uncertain',note='evidence')
        audit.save_review(event);audit.save_review(dict(event,decision='include'))
        with closing(audit.reviews()) as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM reviews')
        with closing(sqlite3.connect(self.primary)) as db,db:
            db.execute("UPDATE trials SET status='error'")
        frozen=audit.freeze_reviews(self.root/'freeze.json')
        self.assertEqual(len(frozen['events']),2)
        self.assertEqual(frozen['latest_decisions'][0]['source_state'],'changed')
        with self.assertRaises(ValueError):audit.freeze_reviews(self.root/'freeze.json')
        audit.scan()
        self.assertEqual(len(list((self.root/'audit-state').glob('inventory-*.json'))),2)

    def test_audit_setup_is_exclusive_and_summaries_reject_mixed_batches(self):
        target=init_audit('AUDIT-1',self.root)
        self.assertTrue((target/'tasks.csv').exists())
        with self.assertRaises(FileExistsError):init_audit('AUDIT-1',self.root)
        with self.assertRaises(ValueError):identifier('../bad')
        rows=[self.record,dict(self.record,id='two',batch_id='other')]
        for summary in (summarize,model_comparison):
            with self.assertRaises(ValueError):summary(rows)
            self.assertEqual(summary(rows,filters={'batch_id':'batch'})['n'],1)

    def test_changed_generation_configuration_cannot_be_pooled(self):
        rows=[dict(self.record,model_parameters={'temperature':0}),dict(self.record,model_parameters={'temperature':1})]
        for summary in (summarize,model_comparison):
            with self.assertRaises(ValueError):summary(rows)

    def test_routes_without_network_preserve_local_origin_and_review_flow(self):
        audit=Audit(self.root,self.root/'audit-state');report=audit.scan()
        key=next(d['key'] for d in report['databases'] if d['path']=='primary.sqlite3')
        cls=handler(audit,8770);h=object.__new__(cls);responses=[]
        h.send=lambda value,status=200,mime=None:responses.append((status,value))
        h.headers={'Host':'127.0.0.1:8770'};h.path='/api/inventory';h.do_GET()
        self.assertEqual(responses[-1][0],200)
        self.assertEqual(responses[-1][1]['inventory_id'],report['inventory_id'])
        h.path='/';h.do_GET();self.assertIn('已有資料審查工作台',responses[-1][1])
        h.path='/workflow';h.do_GET();self.assertIn('EchoMind 工作 SOP',responses[-1][1])
        event=dict(db=key,table='trials',rowid=1,row_hash=digest(audit.row(key,'trials',1)),reviewer='test',decision='uncertain',note='source reviewed')
        payload=json.dumps(event).encode();h.path='/api/review'
        h.headers['Content-Length']=str(len(payload));h.rfile=io.BytesIO(payload)
        h.do_POST();self.assertEqual(responses[-1][0],403)
        h.headers['Origin']='http://127.0.0.1:8770';h.rfile=io.BytesIO(payload)
        h.do_POST();self.assertEqual(responses[-1][0],200)
        h.path='/api/reviews';h.do_GET();self.assertEqual(len(responses[-1][1]),1)


if __name__=='__main__': unittest.main()
