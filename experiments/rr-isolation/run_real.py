"""Bounded RR-ISOLATION-001 sender. Gate A must pass before key access or writes."""
from __future__ import annotations
import argparse,json,os,sqlite3,time,urllib.request,urllib.error,hashlib
from contextlib import contextmanager
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from rr_v05 import load_stimuli
from isolation_protocol import PARAMETERS,OUTPUT_LIMITS,schedule,messages,parse,select_stimuli,price_window,canonical,digest
from journal import require_real_gate,reserve_sent,received

ROOT=Path(__file__).resolve().parent
PRIVATE=ROOT/'private_exports'
DB=PRIVATE/'rr-isolation-001.sqlite3'
ENDPOINT='https://api.deepseek.com/chat/completions'

def request_body(msgs,phase):
    if phase not in OUTPUT_LIMITS:raise ValueError('Unknown phase')
    return {'model':PARAMETERS['model'],'messages':msgs,'stream':False,
            'max_tokens':OUTPUT_LIMITS[phase],'temperature':PARAMETERS['temperature'],
            'thinking':{'type':PARAMETERS['thinking']}}

def charge(usage,window):
    if not isinstance(usage,dict):raise ValueError('Missing usage')
    for k in ('prompt_tokens','completion_tokens'):
        if type(usage.get(k)) is not int or usage[k]<0:raise ValueError('Invalid usage')
    hit=usage.get('prompt_cache_hit_tokens',0)
    if type(hit) is not int or not 0<=hit<=usage['prompt_tokens']:raise ValueError('Invalid cached usage')
    factor=Decimal(2 if window=='peak' else 1)
    return (Decimal(usage['prompt_tokens']-hit)*Decimal('.15')+Decimal(hit)*Decimal('.003')+
            Decimal(usage['completion_tokens'])*Decimal('.60'))*factor/Decimal(1000000)

def http_once(body,key,timeout=90):
    # urllib has no automatic POST retries here. Never persist provider error bodies.
    req=urllib.request.Request(ENDPOINT,data=json.dumps(body,ensure_ascii=False).encode(),
          headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

def send_stage(db,stim,cell,phase,msgs,key='',transport=None):
    """Persist sent before IO; retain returned identity/cost even on invalid output."""
    window=price_window();reserve_sent(db,cell['episode_id'],phase,msgs)
    began=time.monotonic()
    try:
        result=(transport or http_once)(request_body(msgs,phase),key)
    except Exception as exc:
        # The provider may have processed any request whose transmission was attempted.
        with db:
            db.execute("UPDATE requests SET state='ambiguous' WHERE episode_id=? AND phase=?",(cell['episode_id'],phase))
            db.execute("UPDATE episodes SET status='blocked_unknown_request' WHERE episode_id=?",(cell['episode_id'],))
        raise RuntimeError('Request outcome unknown; stop without retry. '+type(exc).__name__) from None
    if not isinstance(result,dict):
        with db:db.execute("UPDATE requests SET state='ambiguous' WHERE episode_id=? AND phase=?",(cell['episode_id'],phase))
        raise RuntimeError('Unusable response envelope; stop without retry')
    rid=result.get('id');model=result.get('model');usage=result.get('usage')
    choice=(result.get('choices') or [{}])[0]
    raw=(choice.get('message') or {}).get('content')
    raw=raw if isinstance(raw,str) else ''
    try:cost=charge(usage,window)
    except ValueError:
        with db:
            db.execute("UPDATE requests SET state='ambiguous',response_id=?,returned_model=?,raw_response=?,usage_json=? WHERE episode_id=? AND phase=?",(rid,model,raw,canonical(usage),cell['episode_id'],phase))
        raise RuntimeError('Response usage incomplete; preserve response and stop') from None
    if not rid:
        with db:db.execute("UPDATE requests SET state='ambiguous',returned_model=?,raw_response=?,usage_json=?,cost_usd=? WHERE episode_id=? AND phase=?",(model,raw,canonical(usage),str(cost),cell['episode_id'],phase))
        raise RuntimeError('Response identity missing; retain usage and stop')
    try:received(db,cell['episode_id'],phase,rid,model,raw,usage,cost)
    except Exception:
        with db:db.execute("UPDATE requests SET state='ambiguous',returned_model=?,raw_response=?,usage_json=?,cost_usd=? WHERE episode_id=? AND phase=?",(model,raw,canonical(usage),str(cost),cell['episode_id'],phase))
        raise RuntimeError('Could not persist response identity; stop without retry') from None
    try:
        if model!=PARAMETERS['model']:raise ValueError('Unexpected returned model')
        if choice.get('finish_reason')!='stop':raise ValueError('Incomplete final output')
        values=parse(raw,stim,cell,phase)
    except (ValueError,TypeError,json.JSONDecodeError):
        with db:
            db.execute("UPDATE requests SET state='invalid' WHERE episode_id=? AND phase=?",(cell['episode_id'],phase))
            db.execute("UPDATE episodes SET status='invalid_response' WHERE episode_id=?",(cell['episode_id'],))
        raise RuntimeError('Response retained but validation failed; no automatic retry') from None
    with db:
        if phase=='rating':
            db.executemany('INSERT INTO ratings VALUES (?,?,?)',[(cell['episode_id'],k,v) for k,v in values.items()])
            db.execute("UPDATE episodes SET status='complete' WHERE episode_id=?",(cell['episode_id'],))
        else:db.execute("UPDATE episodes SET status='encoded' WHERE episode_id=?",(cell['episode_id'],))
        db.execute("UPDATE requests SET state='valid' WHERE episode_id=? AND phase=?",(cell['episode_id'],phase))
    return raw,{'response_id':rid,'model':model,'usage':usage,'cost_usd':str(cost),
                'system_fingerprint':result.get('system_fingerprint'),'latency_ms':round((time.monotonic()-began)*1000),'attempts':1}

def load_key(env_file):
    key=os.environ.get('DEEPSEEK_API_KEY','').strip()
    if not key and env_file:
        for line in Path(env_file).read_text(encoding='utf-8-sig').splitlines():
            name,sep,value=line.partition('=')
            if sep and name.strip()=='DEEPSEEK_API_KEY':key=value.strip().strip('\"\'');break
    if not key:raise RuntimeError('DeepSeek credential is unavailable')
    return key

@contextmanager
def run_lock():
    with (PRIVATE/'real-run.lock').open('a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

def run(args):
    if not args.real:raise RuntimeError('Explicit --real is required')
    report=json.loads((PRIVATE/'gate_a.json').read_text(encoding='utf-8'))
    require_real_gate(report)  # Must precede key access, journal writes, and network access.
    for name,expected in report.get('runtime_file_sha256',{}).items():
        if Path(name).name!=name or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Runtime file changed after Gate A')
    approved_window=report.get('approved_price_window')
    if approved_window not in ('peak','offpeak'):raise RuntimeError('Verified price window missing')
    checked=datetime.fromisoformat(report['observed_utc'])
    if (datetime.now(timezone.utc)-checked).total_seconds()>3600:raise RuntimeError('Gate A checkpoint is stale')
    if os.environ.get('ECHOMIND_OFFLINE')=='1':raise RuntimeError('Offline mode blocks real execution')
    stim=load_stimuli(ROOT/'private_inputs/calm_rr_v42.json')
    plan=schedule(stim);key=load_key(args.env_file)
    with run_lock():
        db=sqlite3.connect(DB);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA synchronous=FULL')
        try:
            config=json.loads(db.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0])
            if config['parameters']!=PARAMETERS or config['stimulus_hash']!=stim['stimulus_set_hash']:raise RuntimeError('Immutable configuration mismatch')
            actual=[tuple(r) for r in db.execute('SELECT episode_id,arm,condition_id,repeat_index,scenario_id,schedule_order FROM episodes ORDER BY schedule_order')]
            expected=[(c['episode_id'],c['arm'],c['condition'],c['repeat'],c['scenario_id'],c['order']) for c in plan]
            if actual!=expected:raise RuntimeError('Episode schedule mismatch')
            if db.execute("SELECT count(*) FROM requests WHERE state!='valid'").fetchone()[0]:raise RuntimeError('Unresolved existing request; stop before any new request')
            independent=report.get('budget_scope')=='independent_20261117'
            prior=Decimal(0) if independent else Decimal(report['reconciled_project_spend_usd'])
            cap=Decimal('.13') if independent else Decimal('.025');totalcap=Decimal('.13') if independent else Decimal('.050')
            bound_file=report.get('preflight_detail_file','preflight_detailed.json')
            if Path(bound_file).name!=bound_file:raise RuntimeError('Invalid private preflight filename')
            bounds={r['episode_id']:r for r in json.loads((PRIVATE/bound_file).read_text())['rows']}
            with db:db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('real_run',canonical({'budget_scope':report.get('budget_scope'),'cap_usd':str(cap),'started_utc':datetime.now(timezone.utc).isoformat(),'gate_hash':digest(report),'parameters':PARAMETERS})))
            for cell in plan:
                encoding=None
                for phase in ('encoding','rating'):
                    existing=db.execute('SELECT * FROM requests WHERE episode_id=? AND phase=?',(cell['episode_id'],phase)).fetchone()
                    if existing:
                        if existing['state']!='valid':raise RuntimeError('Never replay an existing uncertain request')
                        if phase=='encoding':encoding=existing['raw_response']
                        continue
                    if price_window()!=approved_window:raise RuntimeError('Price window changed; stop before next request')
                    spent=sum((Decimal(r[0]) for r in db.execute("SELECT cost_usd FROM requests WHERE state='valid'")),Decimal(0))
                    # Reserve a whole-episode upper bound, including carried encoding output.
                    remaining=Decimal(0)
                    for planned in plan:
                        bound=bounds[planned['episode_id']]
                        for planned_phase in ('encoding','rating'):
                            if db.execute("SELECT 1 FROM requests WHERE episode_id=? AND phase=? AND state='valid'",(planned['episode_id'],planned_phase)).fetchone():continue
                            entry=bound.get(planned_phase)
                            if entry is None:raise RuntimeError('Per-stage whole-pilot bound missing')
                            remaining+=(Decimal(entry['max_input_tokens'])*Decimal('.15')+Decimal(entry['max_output_tokens'])*Decimal('.60'))/1000000
                    if approved_window=='peak':remaining*=2
                    if spent+remaining>cap or prior+spent+remaining>totalcap:raise RuntimeError('Whole remaining matrix budget guard')
                    msgs=messages(stim,cell,phase,encoding)
                    raw,meta=send_stage(db,stim,cell,phase,msgs,key)
                    stage_bound=bounds[cell['episode_id']][phase]
                    if meta['usage']['prompt_tokens']>stage_bound['max_input_tokens'] or meta['usage']['completion_tokens']>stage_bound['max_output_tokens']:
                        raise RuntimeError('Observed usage exceeds reserved bound; stop before next request')
                    if phase=='encoding':encoding=raw
                    with (PRIVATE/'real-events.jsonl').open('a',encoding='utf-8') as f:
                        f.write(json.dumps({'episode_id':cell['episode_id'],'phase':phase,**meta})+'\n');f.flush();os.fsync(f.fileno())
                    print(json.dumps({'episode':cell['order'],'phase':phase,'status':'valid','cost_usd':meta['cost_usd']}),flush=True)
            complete=db.execute("SELECT count(*) FROM episodes WHERE status='complete'").fetchone()[0]
            valid=db.execute("SELECT count(*) FROM requests WHERE state='valid'").fetchone()[0]
            ratings=db.execute('SELECT count(*) FROM ratings').fetchone()[0]
            if (complete,valid,ratings)!=(60,120,432):raise RuntimeError('Incomplete matrix; do not report DONE')
            return {'complete_episodes':complete,'valid_calls':valid,'ratings':ratings}
        finally:db.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--real',action='store_true');p.add_argument('--env-file',type=Path);a=p.parse_args()
    try:print(json.dumps(run(a),indent=2))
    except Exception as e:raise SystemExit(str(e))
