import json,sqlite3
from decimal import Decimal
from pathlib import Path
import pytest
import run_real
from journal import create
from rr_v05 import load_stimuli
from isolation_protocol import schedule,messages,select_stimuli

@pytest.fixture
def setup(tmp_path):
    s=load_stimuli(Path(__file__).resolve().parents[1]/'private_inputs/calm_rr_v42.json')
    p=tmp_path/'unit-only.sqlite3';create(p,s);d=sqlite3.connect(p)
    c=next(c for c in schedule(s) if c['arm']=='ISOLATED')
    yield d,s,c
    d.close()

def response(stim,cell,phase,rid='offline-unit-test',model='deepseek-flash',finish='stop',score=3):
    subset=select_stimuli(stim,cell)
    value={s['id']:'Yes' for s in subset['scenarios']} if phase=='encoding' else {e['item_id']:score for s in subset['scenarios'] for e in s['interpretations']}
    return {'id':rid,'model':model,'usage':{'prompt_tokens':100,'completion_tokens':30,'prompt_cache_hit_tokens':0},
            'choices':[{'finish_reason':finish,'message':{'content':json.dumps(value)}}]}

def test_request_matches_frozen_provider_parameters():
    b=run_real.request_body([{'role':'user','content':'unit-only'}],'encoding')
    assert b=={'model':'deepseek-flash','messages':[{'role':'user','content':'unit-only'}],'stream':False,'max_tokens':800,'temperature':.7,'thinking':{'type':'disabled'}}

def test_sent_marker_is_committed_before_transport(setup):
    d,s,c=setup
    def transport(body,key):
        assert d.execute('SELECT state FROM requests').fetchone()[0]=='sent'
        return response(s,c,'encoding')
    run_real.send_stage(d,s,c,'encoding',messages(s,c,'encoding'),transport=transport)
    assert d.execute('SELECT state FROM requests').fetchone()[0]=='valid'

def test_successful_two_phase_unit_transaction(setup):
    d,s,c=setup
    enc,_=run_real.send_stage(d,s,c,'encoding',messages(s,c,'encoding'),transport=lambda b,k:response(s,c,'encoding','unit-encoding'))
    run_real.send_stage(d,s,c,'rating',messages(s,c,'rating',enc),transport=lambda b,k:response(s,c,'rating','unit-rating'))
    assert d.execute('SELECT count(*) FROM ratings').fetchone()[0]==4
    assert d.execute('SELECT status FROM episodes WHERE episode_id=?',(c['episode_id'],)).fetchone()[0]=='complete'

def test_uncertain_call_never_retried(setup):
    d,s,c=setup;calls=[]
    def broken(body,key):calls.append(1);raise TimeoutError()
    with pytest.raises(RuntimeError):run_real.send_stage(d,s,c,'encoding',messages(s,c,'encoding'),transport=broken)
    with pytest.raises(RuntimeError):run_real.send_stage(d,s,c,'encoding',messages(s,c,'encoding'),transport=broken)
    assert len(calls)==1 and d.execute('SELECT state FROM requests').fetchone()[0]=='ambiguous'

@pytest.mark.parametrize('variant',['wrong-model','truncated','boolean-rating','missing-id'])
def test_invalid_output_retains_cost(setup,variant):
    d,s,c=setup
    phase='rating' if variant=='boolean-rating' else 'encoding'
    if phase=='rating':
        raw,_=run_real.send_stage(d,s,c,'encoding',messages(s,c,'encoding'),transport=lambda b,k:response(s,c,'encoding','unit-enc'))
    else:raw=None
    r=response(s,c,phase,'unit-invalid')
    if variant=='wrong-model':r['model']='unexpected-model'
    if variant=='truncated':r['choices'][0]['finish_reason']='length'
    if variant=='boolean-rating':r=response(s,c,phase,'unit-invalid',score=True)
    if variant=='missing-id':r.pop('id')
    with pytest.raises(RuntimeError):run_real.send_stage(d,s,c,phase,messages(s,c,phase,raw),transport=lambda b,k:r)
    state,cost=d.execute('SELECT state,cost_usd FROM requests WHERE phase=?',(phase,)).fetchone()
    assert state in ('invalid','ambiguous') and Decimal(cost)>0
    assert d.execute('SELECT count(*) FROM ratings').fetchone()[0]==0

def test_current_nogo_precedes_credentials_and_network(monkeypatch,tmp_path):
    def forbidden(*a,**kw):raise AssertionError('Credentials/network accessed while Gate A fails')
    monkeypatch.setattr(run_real,'load_key',forbidden);monkeypatch.setattr(run_real,'http_once',forbidden)
    (tmp_path/'gate_a.json').write_text(json.dumps({'decision':'NO-GO','blockers':['budget']}))
    monkeypatch.setattr(run_real,'PRIVATE',tmp_path)
    args=type('Args',(),{'real':True,'env_file':None})()
    with pytest.raises(RuntimeError,match='NO-GO'):run_real.run(args)

def test_usage_cost_and_missing_usage():
    assert run_real.charge({'prompt_tokens':1000000,'completion_tokens':1000000,'prompt_cache_hit_tokens':0},'offpeak')==Decimal('.75')
    with pytest.raises(ValueError):run_real.charge({},'offpeak')
