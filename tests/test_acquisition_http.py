"""New protocol persistence and protocol isolation through actual offline HTTP."""
import csv
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AcquisitionHTTPTests(unittest.TestCase):
    def test_restart_exports_and_legacy_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            database=Path(folder)/'only-test.sqlite3'
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def api(path,data=None,raw=False):
                request=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
                with opener.open(request,timeout=8) as response:text=response.read().decode('utf-8-sig')
                return text if raw else json.loads(text)
            def start():
                child=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--offline','--port',str(port)],cwd=folder,
                    env={**os.environ,'ECHOMIND_OFFLINE':'1','ECHOMIND_PILOT_DB':str(database),
                         'SOS_PILOT_DB':str(Path(folder)/'must-not-create.sqlite3')},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(100):
                    try:api('/api/acquisition/bootstrap');return child
                    except OSError:time.sleep(.05)
                child.terminate();child.wait();self.fail('server startup failed')
            child=start()
            try:
                self.assertTrue(api('/api/acquisition/bootstrap')['offline'])
                self.assertEqual(api('/api/health')['app_name'],'EchoMind')
                self.assertEqual(api('/api/health')['database'],str(database))
                self.assertFalse((Path(folder)/'must-not-create.sqlite3').exists())
                req={'protocol':'memory_acquisition_v02','mode':'mock','repeats':1,'scenario_ids':['S1_near']}
                preview=api('/api/acquisition/preview',req)
                with closing(sqlite3.connect(database)) as db:
                    self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='acquisition_snapshots'").fetchone())
                job=api('/api/jobs',{**req,'preview_hash':preview['preview_hash']})
                for _ in range(500):
                    finished=api('/api/jobs/'+job['id'])
                    if finished['status'] not in ('queued','running'):break
                    time.sleep(.04)
                self.assertEqual((finished['status'],finished['completed']),('complete',7))
                suffix='?batch_id='+job['id']
                report=api('/api/acquisition/export.json'+suffix)
                self.assertEqual(len(report['snapshots']),7)
                self.assertEqual(len(report['records']),7)
                self.assertEqual(api('/api/trials'),[])
                self.assertEqual(api('/api/mechanism/bootstrap')['batches'],[])
                self.assertEqual(api('/api/ablation/bootstrap')['batches'],[])
                self.assertIn('acquisition_report',api('/api/history/batch'+suffix))
                rows=list(csv.DictReader(io.StringIO(api('/api/acquisition/export.csv'+suffix,raw=True))))
                self.assertTrue(any(r['row_type']=='call_event' for r in rows))
                self.assertEqual(json.loads(next(r['payload_json'] for r in rows if r['row_type']=='decision')),report['records'][0])
                child.terminate();child.wait(timeout=5);child=start()
                again=api('/api/acquisition/report'+suffix)
                for key in ['records','snapshots','call_events','strata']:
                    self.assertEqual(again[key],report[key])
                self.assertEqual(api('/api/jobs/'+job['id']),finished)
            finally:
                if child.poll() is None:child.terminate();child.wait(timeout=5)


if __name__=='__main__':unittest.main()
