"""Local research workflow helpers; no provider calls or source modification."""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

from data_audit import Audit, ROOT, digest, readonly


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1024*1024), b''): h.update(part)
    return h.hexdigest()


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise ValueError('Use an ID containing letters, digits, hyphens or underscores')
    return value


def write_json(path, value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)


def reconcile(primary, backup, destination):
    """Create a trial-only derived audit view; refuse conflicting evidence IDs."""
    primary, backup, destination = map(lambda p:Path(p).resolve(), (primary,backup,destination))
    if destination.exists(): raise ValueError('Recovery directory already exists; use a new ID')
    records, occurrences, counts, inputs = {}, [], {}, []
    primary_ids = set()
    for role,path in [('primary',primary),('backup',backup)]:
        n=0
        with closing(readonly(path)) as db:
            for r in db.execute('SELECT id,created_at,batch_id,source,status,payload FROM trials ORDER BY id'):
                payload = json.loads(r['payload'])
                for field in ('id','batch_id','source','status'):
                    if r[field] != payload.get(field): raise ValueError('Column/payload disagreement: '+str(r['id']))
                identity = digest([r['id'],r['created_at'],r['batch_id'],r['source'],r['status'],payload])
                if r['id'] in records and records[r['id']][0] != identity:
                    raise ValueError('Conflicting ID; recovery refused: '+str(r['id']))
                records.setdefault(r['id'],(identity,tuple(r)))
                occurrences.append((r['id'],role,str(path),identity))
                if role=='primary': primary_ids.add(r['id'])
                n+=1
        counts[role]=n
        inputs.append({'role':role,'path':str(path),'main_file_sha256':sha256(path),
                       'wal_present':Path(str(path)+'-wal').exists(),'rows':n})
    restored = [v[1] for k,v in records.items() if k not in primary_ids]
    destination.mkdir(parents=True)
    target = destination/'reconciled-trials.sqlite3'
    with closing(sqlite3.connect(target)) as db:
        db.executescript('''
            CREATE TABLE trials (id TEXT PRIMARY KEY,created_at TEXT,batch_id TEXT,source TEXT,status TEXT,payload TEXT);
            CREATE TABLE provenance (trial_id TEXT,source_role TEXT,source_path TEXT,semantic_row_hash TEXT);
            CREATE TRIGGER no_trial_update BEFORE UPDATE ON trials BEGIN SELECT RAISE(ABORT,'derived audit view is frozen'); END;
            CREATE TRIGGER no_trial_delete BEFORE DELETE ON trials BEGIN SELECT RAISE(ABORT,'derived audit view is frozen'); END;
        ''')
        with db:
            db.executemany('INSERT INTO trials VALUES (?,?,?,?,?,?)',[v[1] for v in records.values()])
            db.executemany('INSERT INTO provenance VALUES (?,?,?,?)',occurrences)
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Derived database integrity failed')
    result={'created_at':datetime.now(timezone.utc).isoformat(), 'role':'derived_recovery',
            'scope':'trial-only union; no settings, jobs, snapshots or call ledgers restored; not runnable experiment data',
            'inputs':inputs,'source_counts':counts,'union_trials':len(records), 'absent_from_primary':len(restored),
            'recovered_statuses':dict(Counter(str((r[3],r[4])) for r in restored)),
            'output_sha256':sha256(target),'no_source_writes':True}
    write_json(destination/'recovery-manifest.json',result)
    return result


def init_audit(audit_id, root=ROOT):
    audit_id=identifier(audit_id); root=Path(root)
    dest=root/'data'/'local'/'audits'/audit_id
    dest.mkdir(parents=True,exist_ok=False)
    (dest/'reports').mkdir(); (dest/'decisions').mkdir()
    tasks=[('source','Verify source paths, permissions, file fingerprints and copied evidence'),
           ('coverage','Reconcile planned, recorded, complete, failed and missing per frozen batch'),
           ('coding','Review original response, interpretation/action coding and evidence'),
           ('dependence','Record snapshot/episode/item grouping and pairing with missing cells'),
           ('reference','Check human reference provenance, split exposure and no target leakage'),
           ('freeze','Freeze decision history and write next decision; do not auto-include unreviewed rows')]
    (dest/'tasks.csv').write_text('task_id,status,task\n'+''.join(f'{audit_id}-{key},pending,"{label}"\n' for key,label in tasks),encoding='utf-8')
    (dest/'README.md').write_text(f'# {audit_id}\n\nExploratory audit of already observed data.\n\n'
        'Open the repository data review workbench, choose the exact source/batch and record decisions there.\n'
        'Update tasks.csv and put evidence reports in reports/. Use research_ops.py freeze-reviews to save decisions/.\n'
        'Do not copy raw participant rows into public documents. Pending tasks are not completed findings.\n',encoding='utf-8')
    state = subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True)
    write_json(dest/'audit-manifest.json',{'audit_id':audit_id,'created_at':datetime.now(timezone.utc).isoformat(),
                'git_head':state.stdout.strip() or None,'scope':'existing-data exploratory audit', 'status':'open'})
    return dest


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    s=sub.add_parser('init-audit');s.add_argument('id')
    s=sub.add_parser('recover-trials');s.add_argument('--primary',required=True,type=Path);s.add_argument('--backup',required=True,type=Path);s.add_argument('--id',required=True)
    s=sub.add_parser('freeze-reviews');s.add_argument('--audit-id',required=True);s.add_argument('--version',required=True);s.add_argument('--base',type=Path,default=ROOT)
    a=p.parse_args()
    try:
        if a.action=='init-audit': print(init_audit(a.id))
        elif a.action=='recover-trials':
            result=reconcile(a.primary,a.backup,ROOT/'data'/'local'/'derived'/identifier(a.id))
            print(json.dumps(result,ensure_ascii=False,indent=2))
        else:
            dest=ROOT/'data'/'local'/'audits'/identifier(a.audit_id)/'decisions'/('reviews-'+identifier(a.version)+'.json')
            if not (dest.parent.parent/'audit-manifest.json').exists(): raise ValueError('Initialize the audit first')
            audit=Audit(a.base);audit.scan();audit.freeze_reviews(dest);print(dest)
    except (ValueError,OSError,sqlite3.Error) as exc:
        print(str(exc),file=sys.stderr);return 1
    return 0


if __name__=='__main__': raise SystemExit(main())
