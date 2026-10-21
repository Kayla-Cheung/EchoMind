"""Offline regression tests for recovery, isolation, circuit breakers and versions."""
import copy
import csv
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import socket
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storage import Store
from history import batches, batch_report, export, import_records, select_records, parse_import_json
from runner import JobManager
from model_client import ProviderError, call, make_spec
from prompt_registry import BUILTINS, catalog, preview, save_bundle, validate_multiaxis


def record(rid="old", batch="batch", protocol="memory-ratio-v1", source="LIVE_LLM_API", status="complete"):
    return {"id": rid, "batch_id": batch, "timestamp": "2026-10-20T17:00:00+00:00", "source": source,
            "protocol": protocol, "status": status, "model": "model-old", "condition": "c",
            "coder_version": "original-v1", "narrative": "可能忙，也可能不想见我。", "role_messages": [{"role":"user","content":"original"}],
            "evaluator_messages": [{"role":"user","content":"blind original"}],
            "machine_coding": {"interpretation": "negative", "action": "wait", "coding_reason": "original reason"},
            "unknown_future_field": {"must": "survive"}, "error": None}


class StoreFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.store = Store(self.path)

    def payloads(self):
        with self.store.connection() as db:
            return [tuple(r) for r in db.execute("SELECT id,payload FROM trials ORDER BY id")]


class RecoveryTests(StoreFixture, unittest.TestCase):

    def test_persistence_import_idempotence_backup_and_unknown_fields(self):
        original = record()
        self.store.add_trial(original)
        before = self.payloads()
        document = export([original, record("new", "batch2", "future-v9", status="error")])
        report = import_records(self.store, document)
        self.assertEqual(self.payloads(), before)
        self.assertEqual(report["new_n"], 1)
        result = import_records(self.store, document, commit=True, expected_digest=report["digest"])
        with closing(sqlite3.connect(result["backup"])) as backup:
            self.assertEqual(backup.execute("SELECT id,payload FROM trials").fetchall(), before)
        reopened = Store(self.path)
        self.assertEqual(sorted(reopened.trials(),key=lambda r:r["id"]), sorted(document["records"],key=lambda r:r["id"]))
        after = self.payloads()
        result = import_records(reopened, document, commit=True, expected_digest=report["digest"])
        self.assertEqual(result["imported"], 0)
        self.assertIsNone(result["backup"])
        self.assertEqual(self.payloads(), after)
        self.assertIn(before[0], after)

    def test_conflict_invalid_file_and_secret_reject_atomically(self):
        self.store.add_trial(record())
        before = self.payloads()
        changed = {**record(), "narrative": "different"}
        for document in ([record("new"), changed], [record("duplicate"), {**record("duplicate"), "status":"error"}]):
            result = import_records(self.store, document)
            self.assertTrue(result["conflicts"])
            with self.assertRaises(ValueError):
                import_records(self.store, document, commit=True, expected_digest=result["digest"])
            self.assertEqual(self.payloads(), before)
        for document in ([{"negative":19}], [{**record("new"),"api_key":"synthetic-secret"}],
                         [{**record("new"),"timestamp":"2026-01-01"}], [{**record("new"),"x":float("nan")}], []):
            self.assertRaises(ValueError, import_records, self.store, document)
        doc = export([record("new")])
        self.assertRaises(ValueError, import_records, self.store, doc, commit=True, expected_digest="stale")
        doc["records"][0]["status"] = "error"
        self.assertRaises(ValueError, import_records, self.store, doc)
        self.assertEqual(self.payloads(), before)

    def test_raw_json_preserves_64_bit_seeds_and_rejects_duplicate_keys(self):
        row={**record(),"seed":9223372036854775801,"temperature":1.0}
        doc=export([row])
        parsed=parse_import_json(json.dumps(doc))
        self.assertEqual(parsed["records"][0]["seed"],row["seed"])
        self.assertIsInstance(parsed["records"][0]["temperature"],float)
        peek=import_records(self.store,parsed)
        import_records(self.store,parsed,commit=True,expected_digest=peek["digest"])
        self.assertEqual(self.store.trials(),[row])
        self.assertRaises(ValueError,parse_import_json,'{"records":[],"records":[]}')
        self.assertRaises(ValueError,parse_import_json,'{"x":NaN}')

    def test_all_protocols_failure_filters_and_denominators(self):
        rows = [record(), record("b","b","memory-ablation-v1"), record("failed","failed",status="error"),
                record("mock","mock",source="MOCK_NOT_LLM"), record("legacy","legacy",protocol=None)]
        self.assertEqual(len(batches(rows)), 5)
        self.assertEqual(len(batches(rows,{"from":"2026-10-21","to":"2026-10-21"})),5)
        self.assertEqual(len(batches(rows,{"from":"2026-10-22"})),0)
        self.assertEqual(len(batches(rows,{"model":"model-old","protocol":"memory-ablation-v1"})),1)
        self.assertEqual(batches(rows,{"status":"error"})[0]["id"],"failed")
        self.assertEqual(batch_report(rows,"failed")["cells"][0]["coded_n"],0)
        self.assertEqual(select_records(rows,{"protocol":"legacy-unspecified"}),[rows[-1]])
        # Even malformed mixed batches never pool protocols, sources or model params.
        mixed=[record("a"), record("b",protocol="memory-ablation-v1"), record("c",source="MOCK_NOT_LLM"),
               {**record("d"), "model_parameters":{"temperature":2}}]
        report=batch_report(mixed,"batch")
        self.assertEqual(len(report["cells"]),4)
        self.assertIsNone(report["original_report"])

    def test_relative_paths_independent_of_working_directory(self):
        # Resolve a project-relative temporary path, then open it from unrelated cwd.
        relative = os.path.relpath(self.path, ROOT)
        self.store.add_trial(record())
        code = "from storage import Store; import sys,json; s=Store(sys.argv[1]); print(json.dumps([str(s.path),len(s.trials())]))"
        env = {**os.environ, "PYTHONPATH":str(ROOT), "SOS_OFFLINE":"1"}
        result = subprocess.check_output([sys.executable,"-c",code,relative],cwd=self.temp.name,env=env,text=True)
        self.assertEqual(json.loads(result),[str(self.path.resolve()),1])

    def test_prompt_versions_immutable_blind_and_reopened(self):
        a=copy.deepcopy(BUILTINS[0]); a.update(version="agent-minimal-v2.1", parent=BUILTINS[0]["version"])
        saved=save_bundle(self.store,a)
        self.assertEqual(catalog(Store(self.path))[-1],saved)
        self.assertRaises(ValueError,save_bundle,self.store,a)
        a.update(version="agent-minimal-v2.2",coder_user=a["coder_user"]+"new rule")
        self.assertRaises(ValueError,save_bundle,self.store,a)
        result=preview(BUILTINS[0],"name","identity","SCENARIO","PRIVATE_OWNER","PRIVATE_MEMORY","RESPONSE")
        coder=json.dumps(result["evaluator_messages"])
        self.assertNotIn("PRIVATE_OWNER",coder);self.assertNotIn("PRIVATE_MEMORY",coder)
        self.assertIn("SCENARIO",coder);self.assertIn("RESPONSE",coder)
        a=copy.deepcopy(BUILTINS[0]);a["coder_user"]+="$owner"
        self.assertRaises(ValueError,preview,a,"name","identity","scene","owner","events")

    def test_multiaxis_evidence_cannot_invent_busy(self):
        coding={k:{"value":"absent","evidence":[]} for k in ("negative_attribution","benign_attribution","negative_affect","explicit_memory_link")}
        coding.update(negative_commitment="possible",negative_target=["other"],actions=[],action_observability="absent",uncertainty_note="")
        coding["negative_attribution"]={"value":"present","evidence":["不想理我"]}
        validate_multiaxis(coding,"他是不是不想理我")
        coding["benign_attribution"]={"value":"present","evidence":["对方忙"]}
        self.assertRaises(ValueError,validate_multiaxis,coding,"他是不是不想理我")


class CircuitTests(StoreFixture, unittest.TestCase):
    def wait_job(self, jobs, jid):
        for _ in range(200):
            job=jobs.get(jid)
            if job["status"] not in ("queued","running"): return job
            time.sleep(.01)
        self.fail("job did not finish")

    def start_failure(self, kind, concurrency=1):
        jobs=JobManager(self.store)
        request={"mode":"live","repeats":10,"conditions":["baseline"],"concurrency":concurrency}
        with patch("runner.offline_mode",return_value=False), patch("runner.call",side_effect=ProviderError("synthetic failure",kind)) as transport:
            first=jobs.start(request)
            result=self.wait_job(jobs,first["id"])
            return result,transport.call_count

    def test_authentication_stops_and_restart_restores_batch(self):
        job,calls=self.start_failure("authentication")
        self.assertEqual(calls,1);self.assertEqual(job["unissued"],9)
        self.assertEqual(job["stop_reason"],"authentication")
        self.assertEqual(JobManager(Store(self.path)).get(job["id"]),job)
        self.assertEqual(len(self.store.trials()),1)

    def test_rate_limit_stops_after_transport_retries(self):
        spec=make_spec({"provider":"deepseek"})
        def failure(*args):raise urllib.error.HTTPError("https://example.invalid",429,"test",{},io.BytesIO(b'synthetic-secret'))
        with patch("model_client.time.sleep"),patch("model_client.os.getenv",side_effect=AssertionError("must not read credentials")):
            # offline_mode reads only SOS_OFFLINE, so separately stub it.
            with patch("model_client.offline_mode",return_value=True):
                with self.assertRaises(ProviderError) as caught:call(spec,[{"role":"user","content":"x"}],transport=failure)
        self.assertEqual(caught.exception.meta["attempts"],3)
        self.assertNotIn("synthetic-secret",str(caught.exception))
        job,calls=self.start_failure("rate_limit")
        self.assertEqual((calls,job["unissued"]),(1,9))

    def test_consecutive_failures_and_bounded_concurrency(self):
        job,calls=self.start_failure("transport")
        self.assertEqual((calls,job["unissued"]),(3,7))
        job,calls=self.start_failure("authentication",concurrency=3)
        self.assertLessEqual(calls,3);self.assertEqual(job["unissued"],10-calls)

    def test_interrupted_queue_not_auto_resumed_or_rewritten(self):
        r=record(status="running");self.store.add_trial(r)
        before=self.payloads()
        self.store.save_setting("job:batch",{"id":"batch","status":"running","total":20})
        result=JobManager(Store(self.path)).get("batch")
        self.assertEqual(result["status"],"interrupted")
        self.assertEqual(self.payloads(),before)

    def test_offline_guard_precedes_key_access(self):
        with patch("runner.offline_mode",return_value=True):
            self.assertRaises(ValueError,JobManager(self.store).start,{"mode":"live"})
        with patch("model_client.offline_mode",return_value=True),patch("model_client.os.getenv",side_effect=AssertionError("credentials read")):
            self.assertRaises(ProviderError,call,make_spec({"provider":"deepseek"}),[{"role":"user","content":"test"}])


class HistoryHTTPTests(StoreFixture, unittest.TestCase):
    def start_server(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); self.port=sock.getsockname()[1]
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.process=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--offline','--port',str(self.port)],
            cwd=self.temp.name,env={**os.environ,'SOS_OFFLINE':'1','SOS_PILOT_DB':str(self.path)},
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_server)
        for _ in range(80):
            try:self.request('/api/health');return
            except OSError:time.sleep(.05)
        self.fail('server did not start')

    def stop_server(self):
        if self.process.poll() is None:
            self.process.terminate();self.process.wait(timeout=5)

    def request(self,path,data=None,raw=False):
        request=urllib.request.Request(f'http://127.0.0.1:{self.port}'+path,
            data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with self.opener.open(request,timeout=5) as response:
            text=response.read().decode('utf-8-sig')
        return text if raw else json.loads(text)

    def test_import_export_mock_run_and_restart_end_to_end(self):
        self.start_server()
        self.assertTrue(self.request('/api/health')['offline'])
        records=[record('a','a'), record('b','b','memory-ablation-v1',status='error'),record('c','c',protocol=None)]
        document=export(records)
        peek=self.request('/api/history/import/preview',{'document':document})
        self.assertEqual(self.request('/api/history/batches')['total_records'],0)
        commit=self.request('/api/history/import/commit',{'document':document,'digest':peek['digest']})
        self.assertEqual(commit['imported'],3);self.assertTrue(Path(commit['backup']).exists())
        again=self.request('/api/history/import/commit',{'document':document,'digest':peek['digest']})
        self.assertEqual(again['imported'],0)
        self.assertEqual(self.request('/api/history/export.json')['records'],records)
        csv_rows=list(csv.DictReader(io.StringIO(self.request('/api/history/export.csv',raw=True))))
        self.assertEqual([json.loads(r['record_json']) for r in csv_rows],records)
        self.assertEqual(json.loads(csv_rows[0]['role_messages_json']),records[0]['role_messages'])
        self.assertEqual(len(self.request('/api/history/batches?protocol=memory-ablation-v1&status=error')['batches']),1)
        self.assertEqual(len(self.request('/api/history/export.json?batch_id=b')['records']),1)
        self.assertEqual(self.request('/api/history/batch?batch_id=b')['records'],[records[1]])
        with self.assertRaises(urllib.error.HTTPError) as caught:self.request('/api/jobs',{'mode':'live'})
        self.assertEqual(caught.exception.code,400)
        job=self.request('/api/jobs',{'mode':'mock','repeats':3,'conditions':['baseline']})
        for _ in range(100):
            finished=self.request('/api/jobs/'+job['id'])
            if finished['status'] not in ('queued','running'):break
            time.sleep(.03)
        self.assertEqual(finished['status'],'complete');self.assertEqual(finished['completed'],3)
        bundle={**BUILTINS[0],'version':'http-test-v2.1','parent':BUILTINS[0]['version']}
        saved=self.request('/api/prompts',bundle)
        self.assertEqual(self.request('/api/prompts/preview',{'version':saved['version']})['mode'],'offline_template_preview')
        before=self.payloads()
        self.stop_server();self.start_server()
        self.assertEqual(self.request('/api/history/batches')['total_records'],6)
        self.assertEqual(self.request('/api/jobs/'+job['id']),finished)
        self.assertEqual(self.payloads(),before)
        self.assertIn(saved['version'],[v['version'] for v in self.request('/api/prompts')['versions']])


if __name__ == "__main__": unittest.main()
