"""New experiment journal. Existing experiment databases are never opened writable."""
import json,sqlite3
from pathlib import Path
from datetime import datetime,timezone
from isolation_protocol import PROTOCOL,PARAMETERS,canonical,digest,schedule

SCHEMA='''
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE episodes(episode_id TEXT PRIMARY KEY,arm TEXT NOT NULL,condition_id TEXT NOT NULL,
 repeat_index INTEGER NOT NULL,scenario_id TEXT NOT NULL,schedule_order INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'planned',
 UNIQUE(arm,condition_id,repeat_index,scenario_id));
CREATE TABLE requests(episode_id TEXT NOT NULL,phase TEXT NOT NULL CHECK(phase IN ('encoding','rating')),
 state TEXT NOT NULL CHECK(state IN ('sent','received','valid','invalid','ambiguous')),
 prompt_hash TEXT NOT NULL,messages_json TEXT NOT NULL,started_at TEXT NOT NULL,
 response_id TEXT UNIQUE,returned_model TEXT,raw_response TEXT,usage_json TEXT,cost_usd TEXT,
 PRIMARY KEY(episode_id,phase),FOREIGN KEY(episode_id) REFERENCES episodes(episode_id));
CREATE TABLE ratings(episode_id TEXT NOT NULL,item_id TEXT NOT NULL,rating INTEGER NOT NULL
 CHECK(typeof(rating)='integer' AND rating BETWEEN 1 AND 4),PRIMARY KEY(episode_id,item_id),
 FOREIGN KEY(episode_id) REFERENCES episodes(episode_id));
'''

def readonly(path):
    path=Path(path)
    if not path.exists():raise FileNotFoundError(path)
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db

def create(path,stimuli):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive filesystem creation prevents accidental reuse/overwrite of a prior run.
    with path.open('xb'):pass
    d=sqlite3.connect(path)
    try:
        d.execute('PRAGMA foreign_keys=ON');d.executescript(SCHEMA)
        cfg={'protocol':PROTOCOL,'parameters':PARAMETERS,'stimulus_hash':stimuli['stimulus_set_hash'],'seed':20261116}
        d.execute('INSERT INTO meta VALUES (?,?)',('config',canonical(cfg)))
        d.execute('INSERT INTO meta VALUES (?,?)',('created_at',datetime.now(timezone.utc).isoformat()))
        d.executemany('INSERT INTO episodes(episode_id,arm,condition_id,repeat_index,scenario_id,schedule_order) VALUES (?,?,?,?,?,?)',
          [(c['episode_id'],c['arm'],c['condition'],c['repeat'],c['scenario_id'],c['order']) for c in schedule(stimuli)])
        d.commit()
    finally:d.close()

def reserve_sent(db,episode_id,phase,messages):
    """Commit before transmission. Every existing record forbids automatic resend."""
    if phase not in ('encoding','rating'):raise ValueError('Unknown phase')
    db.execute('BEGIN IMMEDIATE')
    try:
        if not db.execute('SELECT 1 FROM episodes WHERE episode_id=?',(episode_id,)).fetchone():raise ValueError('Unknown episode')
        if db.execute('SELECT 1 FROM requests WHERE episode_id=? AND phase=?',(episode_id,phase)).fetchone():raise RuntimeError('Existing request: stop; do not replay')
        if phase=='rating' and not db.execute("SELECT 1 FROM requests WHERE episode_id=? AND phase='encoding' AND state='valid'",(episode_id,)).fetchone():raise RuntimeError('Encoding not valid')
        db.execute('INSERT INTO requests(episode_id,phase,state,prompt_hash,messages_json,started_at) VALUES (?,?,?,?,?,?)',
          (episode_id,phase,'sent',digest(messages),canonical(messages),datetime.now(timezone.utc).isoformat()))
        db.commit()
    except:db.rollback();raise

def received(db,episode_id,phase,response_id,model,raw,usage,cost):
    if not response_id or not isinstance(usage,dict):raise ValueError('Response identity and usage required')
    with db:
        n=db.execute("UPDATE requests SET state='received',response_id=?,returned_model=?,raw_response=?,usage_json=?,cost_usd=? WHERE episode_id=? AND phase=? AND state='sent'",(response_id,model,raw,canonical(usage),str(cost),episode_id,phase)).rowcount
        if n!=1:raise RuntimeError('Unexpected request transition')

def require_real_gate(report):
    independent=(report.get('budget_scope')=='independent_20261117' and
                 report.get('owner_authorized_incremental_usd')=='0.13' and
                 report.get('history_reconciliation_deferred_by_owner') is True)
    verified_tokenizer=(report.get('official_tokenizer_verified') is True and report.get('official_chat_template_verified') is True)
    if report.get('decision')!='GO' or report.get('blockers') or not (report.get('exact_template_verified') or verified_tokenizer) or not (report.get('provider_billing_reconciled') or independent):
        raise RuntimeError('NO-GO: Gate A incomplete. No model request is permitted.')
    from decimal import Decimal
    cost=report.get('cost',{})
    cap=Decimal('.13') if independent else Decimal('.025')
    if Decimal(cost.get('offpeak_diagnostic_usd','Infinity'))>cap:
        raise RuntimeError('NO-GO: full design exceeds incremental cap')
    if not independent and Decimal(report.get('reconciled_project_spend_usd','Infinity'))+Decimal(cost.get('offpeak_diagnostic_usd','Infinity'))>Decimal('.050'):
        raise RuntimeError('NO-GO: project cumulative cap')

def status(path):
    d=readonly(path)
    try:
        episodes=[dict(r) for r in d.execute('SELECT * FROM episodes ORDER BY schedule_order')]
        counts={t:d.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('episodes','requests','ratings')}
        valid=d.execute("SELECT count(*) FROM requests WHERE state='valid'").fetchone()[0]
        return {'episodes':episodes,'counts':counts,'valid_requests':valid,'complete':sum(r['status']=='complete' for r in episodes)}
    finally:d.close()
