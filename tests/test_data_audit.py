"""Preservation, duplicate/conflict detection and review provenance checks."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_audit import Audit, digest, readonly
from clean_mock_data import purge_mock_data
from analysis import summarize


class DataAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.path = self.base/'a.sqlite3'
        self.record = {'id':'t1','batch_id':'b1','source':'LIVE_LLM_API','status':'error'}
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE trials (id TEXT PRIMARY KEY, created_at TEXT, batch_id TEXT, source TEXT, status TEXT, payload TEXT)')
            db.execute('INSERT INTO trials VALUES (?,?,?,?,?,?)',('t1','2026-01-01','b1','LIVE_LLM_API','error',json.dumps(self.record)))
        self.audit = Audit(self.base, self.base/'private_exports')

    def tearDown(self): self.temp.cleanup()

    def test_readonly_scan_preserves_failures_and_detects_copies_and_conflicts(self):
        shutil.copyfile(self.path,self.base/'b.sqlite3')
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        report = self.audit.scan()
        self.assertEqual(report['unique_trial_ids'],1)
        self.assertEqual(report['identical_extra_copies'],1)
        self.assertEqual(report['conflicts'],[])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        with closing(sqlite3.connect(self.base/'b.sqlite3')) as db, db:
            changed = dict(self.record,status='complete')
            db.execute('UPDATE trials SET payload=?',(json.dumps(changed),))
        self.assertEqual(len(self.audit.scan()['conflicts']),1)
        with closing(readonly(self.path)) as db:
            with self.assertRaises(sqlite3.OperationalError): db.execute('DELETE FROM trials')

    def test_review_is_append_only_and_rejects_stale_content(self):
        key = self.audit.scan()['databases'][0]['key']
        row = self.audit.row(key,'trials',1)
        review = dict(db=key,table='trials',rowid=1,row_hash=digest(row),reviewer='test',decision='uncertain',note='Failure retained')
        self.audit.save_review(review)
        self.audit.save_review(dict(review,decision='exclude'))
        with closing(self.audit.reviews()) as db: self.assertEqual(db.execute('SELECT count(*) FROM reviews').fetchone()[0],2)
        with self.assertRaises(ValueError): self.audit.save_review(dict(review,row_hash='stale'))
        with self.assertRaises(ValueError): self.audit.rows(key,'trials; DROP TABLE trials')
        self.assertEqual(self.audit.rows(key,'trials',query='error')['total'],1)

    def test_cleaner_cannot_delete_evidence(self):
        with self.assertRaises(RuntimeError): purge_mock_data(self.path)
        with closing(sqlite3.connect(self.path)) as db, db: self.assertEqual(db.execute('SELECT count(*) FROM trials').fetchone()[0],1)

    def test_missing_coding_is_not_a_negative_rate_denominator(self):
        base = dict(source='LIVE_LLM_API',status='complete',condition='baseline',scenario_id='s1',scenario_kind='social')
        result = summarize([{**base,'machine_coding':{}},{**base,'machine_coding':{'interpretation':'negative','action':'avoid'}}])
        stats = result['by_condition']['baseline']
        self.assertEqual(stats['n'],2)
        self.assertEqual(stats['interpretation_n'],1)
        self.assertEqual(stats['negative_rate'],1)
        self.assertEqual(stats['avoid_rate'],1)

    def test_structured_filters_4axis_coding_pairing_and_blind_packet(self):
        p0 = {
            'id': 'p0_1', 'batch_id': 'b_v03', 'protocol': 'prompt_framing_v03',
            'source': 'LIVE_LLM_API', 'status': 'complete', 'model': 'deepseek-flash',
            'condition': 'negative_direct', 'scenario_id': 'S1', 'scenario_kind': 'social',
            'prompt_variant': 'P0', 'prompt_pair_id': 'snap1:S1', 'memory_snapshot_id': 'snap1',
            'agent_parsed': {'interpretation': '可能只是忙，但我还是怀疑他们针对我', 'speech': '', 'action': '先观望'},
            'narrative': '{"interpretation":"可能只是忙，但我还是怀疑他们针对我","speech":"","action":"先观望"}',
            'machine_coding': {'interpretation': 'neutral', 'action': 'wait', 'coding_confidence': 0.65},
        }
        p1 = {
            'id': 'p1_1', 'batch_id': 'b_v03', 'protocol': 'prompt_framing_v03',
            'source': 'LIVE_LLM_API', 'status': 'complete', 'model': 'deepseek-flash',
            'condition': 'negative_direct', 'scenario_id': 'S1', 'scenario_kind': 'social',
            'prompt_variant': 'P1', 'prompt_pair_id': 'snap1:S1', 'memory_snapshot_id': 'snap1',
            'agent_parsed': {'interpretation': '可能刚好在忙', 'speech': '稍后聊', 'action': '等待'},
            'narrative': '{"interpretation":"可能刚好在忙","speech":"稍后聊","action":"等待"}',
            'machine_coding': {'interpretation': 'neutral', 'action': 'wait', 'coding_confidence': 0.9},
        }
        s4 = {
            'id': 's4_1', 'batch_id': 'b_v03', 'protocol': 'prompt_framing_v03',
            'source': 'LIVE_LLM_API', 'status': 'complete', 'model': 'deepseek-flash',
            'condition': 'negative_direct', 'scenario_id': 'S4_control', 'scenario_kind': 'control',
            'prompt_variant': 'P0', 'prompt_pair_id': 'snap1:S4_control', 'memory_snapshot_id': 'snap1',
            'agent_parsed': {'interpretation': '想起昨天陈晨跳过我的发言', 'speech': '', 'action': '离开'},
            'narrative': '{"interpretation":"想起昨天陈晨跳过我的发言","speech":"","action":"离开"}',
            'machine_coding': {'interpretation': 'negative', 'action': 'avoid', 'coding_confidence': 0.9},
        }
        with closing(sqlite3.connect(self.path)) as db, db:
            for rec in (p0, p1, s4):
                db.execute('INSERT INTO trials VALUES (?,?,?,?,?,?)',
                           (rec['id'], '2026-11-07', rec['batch_id'], rec['source'], rec['status'], json.dumps(rec, ensure_ascii=False)))

        report = self.audit.scan()
        db_info = report['databases'][0]
        key = db_info['key']
        self.assertEqual(db_info['quality_hints'].get('mixed_neutral_risk'), 1)
        self.assertEqual(db_info['quality_hints'].get('s4_memory_spillover'), 1)

        mixed = self.audit.rows(key, 'trials', batch_id='b_v03', flag='mixed_neutral_risk')
        self.assertEqual(mixed['total'], 1)
        self.assertEqual(mixed['rows'][0]['id'], 'p0_1')

        detail = self.audit.row_detail(key, 'trials', mixed['rows'][0]['_audit_rowid_'])
        self.assertEqual(detail['view']['kind'], 'trial')
        self.assertIn('怀疑他们针对我', detail['view']['interpretation'])

        with self.assertRaises(ValueError):
            self.audit.save_review(dict(
                db=key, table='trials', rowid=mixed['rows'][0]['_audit_rowid_'],
                row_hash=detail['hash'], reviewer='coder', decision='include', note='bad axis',
                coding={'threat_attribution': 3},
            ))

        saved = self.audit.save_review(dict(
            db=key, table='trials', rowid=mixed['rows'][0]['_audit_rowid_'],
            row_hash=detail['hash'], reviewer='coder', decision='include', note='mixed attribution verified',
            coding={
                'threat_attribution': 2, 'benign_attribution': 1,
                'memory_intrusion': 0, 'behavioral_avoidance': 1, 'mixed_attribution': True,
            },
        ))
        self.assertEqual(saved['coding']['coding_mode'], 'unblinded_review')
        self.assertEqual(self.audit.rows(key, 'trials', review_status='coded')['total'], 1)
        csv_rev = self.audit.export_reviews_csv()
        self.assertIn('mixed attribution verified', csv_rev)

        paired = self.audit.pairs(key, batch_id='b_v03', mode='prompt')
        self.assertEqual(paired['summary']['total_pairs'], 2)
        self.assertEqual(paired['summary']['complete_pairs'], 1)
        self.assertEqual(paired['summary']['missing_side_pairs'], 1)
        p_csv = self.audit.export_pairing_csv(key, batch_id='b_v03', mode='prompt')
        self.assertIn('missing_side', p_csv)
        self.assertIn('P1', p_csv)

        b_csv, b_map = self.audit.export_blind_packet(key, batch_id='b_v03', source='LIVE_LLM_API', seed='seed-1')
        self.assertEqual(b_map['count'], 3)
        self.assertIn('DO_NOT_GIVE_TO_BLIND_CODERS', b_map['notice'])
        self.assertNotIn('negative_direct', b_csv)
        self.assertNotIn('deepseek-flash', b_csv)
        self.assertNotIn('prompt_framing_v03', b_csv)

    def test_rr_summary_computes_w1_and_contrasts(self):
        rr_db = self.base / 'rr.sqlite3'
        with closing(sqlite3.connect(rr_db)) as db, db:
            db.executescript('''
                CREATE TABLE episodes (episode_id TEXT PRIMARY KEY, batch_id TEXT, prompt_variant TEXT, condition_id TEXT, status TEXT);
                CREATE TABLE requests (request_id TEXT PRIMARY KEY, episode_id TEXT, phase TEXT, requested_model TEXT, returned_model TEXT, parse_status TEXT);
                CREATE TABLE ratings (episode_id TEXT, prompt_variant TEXT, condition_id TEXT, scenario_id TEXT, category TEXT, item_id TEXT, item_type TEXT, rating INTEGER);
                CREATE TABLE human_reference (split_name TEXT, item_id TEXT, n INTEGER, probabilities_json TEXT);
            ''')
            db.execute("INSERT INTO episodes VALUES ('e1','b1','P0','none','complete')")
            db.execute("INSERT INTO episodes VALUES ('e2','b1','P1','none','complete')")
            db.execute("INSERT INTO requests VALUES ('r1','e1','rating','m1','m1','valid')")
            db.execute("INSERT INTO requests VALUES ('r2','e2','rating','m1','m1','valid')")
            db.execute("INSERT INTO ratings VALUES ('e1','P0','none','elevator','social','elevator_1','ns',4)")
            db.execute("INSERT INTO ratings VALUES ('e2','P1','none','elevator','social','elevator_1','ns',1)")
            db.execute("INSERT INTO human_reference VALUES ('heldout','elevator_ns',100,'{\"1\":1.0,\"2\":0.0,\"3\":0.0,\"4\":0.0}')")

        report = self.audit.scan()
        rr_entry = next(d for d in report['databases'] if d['path'] == 'rr.sqlite3')
        self.assertTrue(rr_entry['has_rr'])
        summary = self.audit.rr_summary(rr_entry['key'])
        self.assertEqual(len(summary['contrasts']), 1)
        c = summary['contrasts'][0]
        self.assertEqual(c['a_w1_mean'], 3.0)
        self.assertEqual(c['b_w1_mean'], 0.0)
        self.assertEqual(c['delta_all_mean'], -3.0)


if __name__ == '__main__': unittest.main()
