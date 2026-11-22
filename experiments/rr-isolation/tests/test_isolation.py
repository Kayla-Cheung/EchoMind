import json,sqlite3,itertools,threading,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import pytest
from rr_v05 import load_stimuli,encoding_messages,rating_messages,memory_messages,SYSTEM_PROMPT
from isolation_protocol import schedule,select_stimuli,messages,parse,PARAMETERS,preflight,price_window,w1,analyze,CONDITIONS
from journal import create,readonly,status,reserve_sent,received,require_real_gate

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture(scope='module')
def stim():return load_stimuli(ROOT/'private_inputs/calm_rr_v42.json')

def test_balanced_grid_and_reproducible_order(stim):
    cells=schedule(stim);assert cells==schedule(stim)
    assert len(cells)==len({c['episode_id'] for c in cells})==60
    assert Counter(c['arm'] for c in cells)=={'BATCH':6,'ISOLATED':54}
    counts=Counter((c['arm'],c['condition'],e['item_id']) for c in cells for s in select_stimuli(stim,c)['scenarios'] for e in s['interpretations'])
    assert sum(counts.values())==432 and len(counts)==216 and set(counts.values())=={2}

@pytest.mark.parametrize('condition',CONDITIONS)
def test_batch_byte_equivalent_to_frozen_protocol(stim,condition):
    c=next(c for c in schedule(stim) if c['arm']=='BATCH' and c['condition']==condition)
    assert messages(stim,c,'encoding')==encoding_messages(stim,condition)
    assert messages(stim,c,'rating','{"test":"Yes"}')==rating_messages(stim,condition,'{"test":"Yes"}')

@pytest.mark.parametrize('condition',CONDITIONS)
@pytest.mark.parametrize('scenario_index',range(9))
def test_isolated_content_and_single_memory(stim,condition,scenario_index):
    item=stim['scenarios'][scenario_index]
    c={'arm':'ISOLATED','condition':condition,'scenario_id':item['id']}
    enc=messages(stim,c,'encoding');raw=json.dumps({item['id']:'Yes'});rat=messages(stim,c,'rating',raw)
    assert enc[0]=={'role':'system','content':SYSTEM_PROMPT}
    assert rat[:-2]==enc and rat[-2]=={'role':'assistant','content':raw}
    assert enc[1:-1]==memory_messages(condition)
    assert len(enc)==(2 if condition=='none' else 3)
    assert item['scenario'] in enc[-1]['content']
    assert all(other['scenario'] not in enc[-1]['content'] for other in stim['scenarios'] if other['id']!=item['id'])
    for s in stim['scenarios']:
        for e in s['interpretations']:
            assert e['item_id'] not in enc[-1]['content']
            assert (e['text'] in rat[-1]['content'])==(s['id']==item['id'])
    assert 'all 4 item IDs' in rat[-1]['content'] and 'all 36 item IDs' not in rat[-1]['content']
    assert 'keys are the story IDs' not in enc[-1]['content']

def test_strict_parsing_and_no_boolean_ratings(stim):
    c=next(c for c in schedule(stim) if c['arm']=='ISOLATED')
    chosen=select_stimuli(stim,c);obj={e['item_id']:3 for e in chosen['scenarios'][0]['interpretations']}
    assert len(parse(json.dumps(obj),stim,c,'rating'))==4
    key=next(iter(obj));obj[key]=True
    with pytest.raises(ValueError):parse(json.dumps(obj),stim,c,'rating')
    with pytest.raises(ValueError):parse('{"a":1,"a":2}',stim,c,'rating')
    with pytest.raises(ValueError):messages(stim,c,'rating')

def test_empty_or_unknown_scenario_rejected(stim):
    with pytest.raises(ValueError):messages(stim,{'arm':'ISOLATED','condition':'none','scenario_id':'bad'},'encoding')
    with pytest.raises(ValueError):messages(stim,{'arm':'ISOLATED','condition':'neutral_interactive','scenario_id':'job'},'encoding')

def test_tokenizer_budget_and_valid_json_headroom(stim):
    import zipfile
    from tokenizers import Tokenizer
    from prepare import V05
    with zipfile.ZipFile(V05/'private_exports/prompt_valence_001/restart_20261115_v1/deepseek_v4_tokenizer.zip') as z:tok=Tokenizer.from_str(z.read('deepseek_v4_tokenizer/tokenizer.json').decode())
    p=preflight(stim,tok)
    assert not p['fits_incremental'] and p['output_only_offpeak_upper_budget_usd']=='0.0936'
    assert p['calls']==120 and not p['exact_template_verified'] and p['attempts']==1
    for c in schedule(stim):
        selected=select_stimuli(stim,c)
        for answer in ('Yes','No'):
            enc=json.dumps({s['id']:answer for s in selected['scenarios']},indent=2)
            assert len(tok.encode(enc).ids)<800
        for score in (1,2,3,4):
            rat=json.dumps({e['item_id']:score for s in selected['scenarios'] for e in s['interpretations']},indent=2)
            assert len(tok.encode(rat).ids)<1800

@pytest.mark.parametrize('day,hour,expected',[(16,0,'offpeak'),(16,1,'peak'),(16,4,'offpeak'),(16,6,'peak'),(16,10,'offpeak'),(15,2,'offpeak')])
def test_price_window_boundaries(day,hour,expected):assert price_window(datetime(2026,11,day,hour,tzinfo=timezone.utc))==expected

def test_durable_sent_requests_cannot_be_replayed(tmp_path,stim):
    path=tmp_path/'new.sqlite3';create(path,stim);c=schedule(stim)[0];m=messages(stim,c,'encoding')
    d=sqlite3.connect(path);reserve_sent(d,c['episode_id'],'encoding',m);d.close()
    d=sqlite3.connect(path)
    with pytest.raises(RuntimeError):reserve_sent(d,c['episode_id'],'encoding',m)
    with pytest.raises(RuntimeError):reserve_sent(d,c['episode_id'],'rating',m)
    received(d,c['episode_id'],'encoding','response-test','deepseek-flash','{}',{'prompt_tokens':1,'completion_tokens':1},'0.000001')
    d.close();d=readonly(path)
    assert d.execute('SELECT state FROM requests').fetchone()[0]=='received';d.close()
    assert status(path)['counts']['requests']==1
    with pytest.raises(FileExistsError):create(path,stim)

def test_readonly_rejects_mutation(tmp_path,stim):
    path=tmp_path/'read.sqlite3';create(path,stim);d=readonly(path)
    with pytest.raises(sqlite3.OperationalError):d.execute('DELETE FROM episodes')
    d.close()

def test_real_gate_refuses_nogo_checkpoint(tmp_path,stim):
    report={'decision':'NO-GO','blockers':['budget']}
    with pytest.raises(RuntimeError):require_real_gate(report)
    path=tmp_path/'empty-plan.sqlite3';create(path,stim)
    assert status(path)['counts']['requests']==0

def test_owner_authorized_independent_budget_is_explicit():
    r={'decision':'GO','blockers':[],'budget_scope':'independent_20261117','owner_authorized_incremental_usd':'0.13',
       'history_reconciliation_deferred_by_owner':True,'official_tokenizer_verified':True,'official_chat_template_verified':True,
       'provider_billing_reconciled':False,'cost':{'offpeak_diagnostic_usd':'0.1251792'}}
    require_real_gate(r)
    r['cost']['offpeak_diagnostic_usd']='0.131'
    with pytest.raises(RuntimeError):require_real_gate(r)

def test_fenced_json_same_acceptance_as_frozen_parser(stim):
    c=next(c for c in schedule(stim) if c['arm']=='ISOLATED')
    selected=select_stimuli(stim,c);raw=json.dumps({s['id']:'Yes' for s in selected['scenarios']})
    assert parse('```json\n'+raw+'\n```',stim,c,'encoding')==json.loads(raw)

def test_gate_cannot_waive_incremental_or_cumulative_cap():
    r={'decision':'GO','blockers':[],'exact_template_verified':True,'provider_billing_reconciled':True,'reconciled_project_spend_usd':'.01','cost':{'offpeak_diagnostic_usd':'.03'}}
    with pytest.raises(RuntimeError):require_real_gate(r)
    r['cost']['offpeak_diagnostic_usd']='.024';r['reconciled_project_spend_usd']='.03'
    with pytest.raises(RuntimeError):require_real_gate(r)

def test_item_matched_wasserstein_and_incomplete_rejection(stim):
    assert w1([.5,0,0,.5],[0,.5,.5,0])==1
    rows=[{'arm':c['arm'],'condition':c['condition'],'repeat':c['repeat'],'item_id':e['item_id'],'rating':2} for c in schedule(stim) for s in select_stimuli(stim,c)['scenarios'] for e in s['interpretations']]
    ref={f"{s['id']}_{e['type']}":{'n':10,'probabilities':{'1':0,'2':1,'3':0,'4':0}} for s in stim['scenarios'] for e in s['interpretations']}
    a=analyze(rows,ref,stim)
    assert len(a['items'])==108 and all(x['isolated_minus_batch']==0 for x in a['items'])
    assert {x['items'] for x in a['summaries'] if x['group']=='social12'}=={12}
    with pytest.raises(ValueError):analyze(rows[:-1],ref,stim)
    with pytest.raises(ValueError):analyze(rows[:-1]+[rows[0]],ref,stim)

def test_local_routes_readonly_and_no_raw_db_export(monkeypatch,tmp_path,stim):
    import workbench
    path=tmp_path/'http-unit-only.sqlite3';create(path,stim);monkeypatch.setattr(workbench,'DB',path)
    from workbench import Handler,ThreadingHTTPServer
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));base=f'http://127.0.0.1:{server.server_address[1]}'
    try:
        for route in ('/','/app.js','/style.css','/api/status','/api/results','/api/preview?arm=ISOLATED&condition=negative_direct&scenario=job'):
            with opener.open(base+route,timeout=3) as r:assert r.status==200
        with opener.open(base+'/api/results') as r:assert json.load(r)['w1'] is None
        for route in ('/private_inputs/calm_rr_v42.json','/private_exports/rr-isolation-001.sqlite3','/api/preview?arm=bad'):
            with pytest.raises(urllib.error.HTTPError):opener.open(base+route,timeout=3)
        with pytest.raises(urllib.error.HTTPError) as e:opener.open(urllib.request.Request(base+'/api/run',data=b'{}'),timeout=3)
        assert e.value.code==405
    finally:server.shutdown();server.server_close();thread.join(3)
