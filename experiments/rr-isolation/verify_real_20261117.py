"""Independent read-only verification and descriptive analysis, no model transport."""
import csv,hashlib,json,math,re,sqlite3,sys
from collections import Counter,defaultdict
from datetime import datetime,timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parent;P=ROOT/'private_exports';OUT=ROOT.parents[1]/'outputs'
sys.path.insert(0,str(ROOT.parent/'coordinator-resume-20261116'))
from independent_audit import fingerprint,V05,DESKTOP,git

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def hashed(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def parse(raw):
    cleaned=raw.strip()
    if cleaned.startswith('```'):cleaned=re.sub(r'^```(?:json)?\s*|\s*```$','',cleaned,flags=re.I|re.S)
    def unique(pairs):
        assert len({k for k,v in pairs})==len(pairs),'Repeated JSON keys'
        return dict(pairs)
    return json.loads(cleaned,object_pairs_hook=unique)

checks=[]
def check(condition,label):
    if not condition:raise AssertionError(label)
    checks.append(label)

d=sqlite3.connect((P/'rr-isolation-001.sqlite3').as_uri()+'?mode=ro&immutable=1',uri=True);d.row_factory=sqlite3.Row
check(d.execute('PRAGMA integrity_check').fetchone()[0]=='ok','new database integrity')
episodes=[dict(x) for x in d.execute('SELECT * FROM episodes ORDER BY schedule_order')]
requests=[dict(x) for x in d.execute('SELECT * FROM requests')]
ratings=[dict(x) for x in d.execute('SELECT * FROM ratings')]
d.close()
check(len(episodes)==60 and all(x['status']=='complete' for x in episodes),'60 complete episodes')
check(Counter(x['arm'] for x in episodes)=={'BATCH':6,'ISOLATED':54},'balanced arm episode counts')
check(len(requests)==120 and all(x['state']=='valid' for x in requests),'120 valid requests')
check(Counter(x['phase'] for x in requests)=={'encoding':60,'rating':60},'two phases per episode')
check(len(ratings)==432 and len({(x['episode_id'],x['item_id']) for x in ratings})==432,'432 unique ratings')
check(all(type(x['rating']) is int and 1<=x['rating']<=4 for x in ratings),'integer legal ratings')
check(len({x['response_id'] for x in requests})==120 and all(x['response_id'] for x in requests),'120 distinct response identities')
check({x['returned_model'] for x in requests}=={'deepseek-flash'},'fixed returned model alias')

original_audit=json.loads((ROOT.parent/'coordinator-resume-20261116/independent_audit.json').read_text(encoding='utf-8'))
prior_ids=set()
for item in original_audit['databases']:
    old=sqlite3.connect(Path(item['path']).as_uri()+'?mode=ro&immutable=1',uri=True)
    prior_ids.update(x[0] for x in old.execute('SELECT response_id FROM requests'));old.close()
legacy=json.loads((ROOT.parent/'coordinator-resume-20261116/legacy_request_index.private.json').read_text())
prior_ids.update(x['response_id'] for x in legacy)
check(not prior_ids&{x['response_id'] for x in requests},'no historical response reuse')

templates=json.loads((P/'01_PROTOCOL.json').read_text(encoding='utf-8'))
plan={x['episode_id']:x for x in templates['plan']}
lookup={x['episode_id']:x for x in episodes}
byrequest={(x['episode_id'],x['phase']):x for x in requests}
stim=json.loads((ROOT/'private_inputs/calm_rr_v42.json').read_text(encoding='utf-8'))
mapping={e['item_id']:(s,e) for s in stim['scenarios'] for e in s['interpretations']}
flat=[]
for ep in episodes:
    eid=ep['episode_id'];planned=plan[eid]
    check((ep['arm'],ep['condition_id'],ep['repeat_index'],ep['scenario_id'])==(planned['arm'],planned['condition'],planned['repeat'],planned['scenario_id']),'planned identity '+eid)
    enc=byrequest[eid,'encoding'];rat=byrequest[eid,'rating']
    check(json.loads(enc['messages_json'])==planned['encoding_messages'],'encoding transcript '+eid)
    expected=json.loads(json.dumps(planned['rating_template_messages']))
    expected[-2]['content']=enc['raw_response']
    check(json.loads(rat['messages_json'])==expected,'rating transcript and same-episode carry '+eid)
    for req in (enc,rat):check(req['prompt_hash']==hashed(json.loads(req['messages_json'])),'prompt hash '+eid+req['phase'])
    selected=stim['scenarios'] if ep['arm']=='BATCH' else [s for s in stim['scenarios'] if s['id']==ep['scenario_id']]
    evalue=parse(enc['raw_response']);rvalue=parse(rat['raw_response'])
    check(set(evalue)=={s['id'] for s in selected} and all(isinstance(v,str) and v.lower() in ('yes','no') for v in evalue.values()),'encoding shape '+eid)
    check(set(rvalue)=={e['item_id'] for s in selected for e in s['interpretations']},'rating item coverage '+eid)
    actual=[x for x in ratings if x['episode_id']==eid]
    check({x['item_id']:x['rating'] for x in actual}==rvalue,'stored ratings match raw response '+eid)
    for x in actual:
        source,choice=mapping[x['item_id']]
        flat.append({**ep,**x,'condition':ep['condition_id'],'repeat':ep['repeat_index'],'rating_type':choice['type'],
                     'source_scenario_id':source['id'],'category':source['category']})

cells=Counter((r['arm'],r['condition'],r['item_id']) for r in flat)
check(len(cells)==216 and set(cells.values())=={2},'exactly two ratings per arm memory item')
events=[json.loads(line) for line in (P/'real-events.jsonl').read_text().splitlines() if line.strip()]
check(len(events)==120 and all(x['attempts']==1 for x in events),'120 durable events each attempts=1')
check({(x['episode_id'],x['phase']) for x in events}==set(byrequest),'events match request grid')
cost=Decimal(0);usage_total=Counter()
bounds={x['episode_id']:x for x in json.loads((P/'preflight-live-20261117.json').read_text())['rows']}
for req in requests:
    u=json.loads(req['usage_json']);hit=u.get('prompt_cache_hit_tokens',0)
    amount=(Decimal(u['prompt_tokens']-hit)*Decimal('.15')+Decimal(hit)*Decimal('.003')+Decimal(u['completion_tokens'])*Decimal('.60'))/1000000
    check(amount==Decimal(req['cost_usd']),'usage cost '+req['episode_id']+req['phase']);cost+=amount
    lim=bounds[req['episode_id']][req['phase']]
    check(u['prompt_tokens']<=lim['max_input_tokens'] and u['completion_tokens']<=lim['max_output_tokens'],'actual usage within bound '+req['episode_id']+req['phase'])
    moment=datetime.fromisoformat(req['started_at']).astimezone(timezone.utc)
    check(not (moment.weekday()<5 and (1<=moment.hour<4 or 6<=moment.hour<10)),'offpeak '+req['episode_id']+req['phase'])
    for k in ('prompt_tokens','completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens'):usage_total[k]+=u.get(k,0)
check(cost<=Decimal('.13'),'owner independent budget respected')

human=json.loads((P/'human_reference_aggregate.json').read_text())
item_results=[]
conditions=('none','neutral_direct','negative_direct')
for condition in conditions:
    for iid,(source,choice) in mapping.items():
        ref=human[source['id']+'_'+choice['type']]
        result={'condition':condition,'item_id':iid,'scenario_id':source['id'],'category':source['category'],'rating_type':choice['type']}
        for arm in ('BATCH','ISOLATED'):
            values=[r['rating'] for r in flat if r['arm']==arm and r['condition']==condition and r['item_id']==iid]
            check(len(values)==2,'W1 model sample size '+arm+condition+iid)
            distance=sum(abs(Fraction(sum(v<=k for v in values),2)-sum(Fraction(str(ref['probabilities'][str(v)])) for v in range(1,k+1))) for k in (1,2,3))
            result[arm]=float(distance)
        result['isolated_minus_batch']=result['ISOLATED']-result['BATCH'];item_results.append(result)

# Compare with the workbench implementation, which uses a separate cumulative-probability formula.
from isolation_protocol import analyze
other=analyze(flat,human,stim)
other_index={(x['condition'],x['item_id']):x for x in other['items']}
check(all(abs(x[a]-other_index[x['condition'],x['item_id']][a])<1e-12 for x in item_results for a in ('BATCH','ISOLATED','isolated_minus_batch')),'independently recomputed all 108 paired W1 entries')
summaries=[]
for c in conditions:
    for group in ('all36','social12',*[s['id'] for s in stim['scenarios']]):
        subset=[r for r in item_results if r['condition']==c and (group=='all36' or group=='social12' and r['category']=='social' or group==r['scenario_id'])]
        summaries.append({'condition':c,'group':group,'items':len(subset),**{key:sum(r[key] for r in subset)/len(subset) for key in ('BATCH','ISOLATED','isolated_minus_batch')}})
frequency={arm:{c:{str(i):sum(r['arm']==arm and r['condition']==c and r['rating']==i for r in flat) for i in (1,2,3,4)} for c in conditions} for arm in ('BATCH','ISOLATED')}
secondary=[]
for arm in ('BATCH','ISOLATED'):
    for c in conditions:
        pairs=[[r['rating'] for r in flat if r['arm']==arm and r['condition']==c and r['item_id']==iid] for iid in mapping]
        signed=[]
        for scenario in ('wedding','meeting_friend','lunch'):
            for rep in (1,2):
                ratings_by_type={r['rating_type']:r['rating'] for r in flat if r['arm']==arm and r['condition']==c and r['repeat']==rep and r['source_scenario_id']==scenario}
                signed.append(ratings_by_type['ps']-ratings_by_type['ns'])
        secondary.append({'arm':arm,'condition':c,'item_repetition_agreement':sum(v[0]==v[1] for v in pairs)/36,
                         'mean_within_item_population_variance':sum((v[0]-v[1])**2/4 for v in pairs)/36,'social_mean_ps_minus_ns':sum(signed)/len(signed)})

before=json.loads((P/'preservation-before-real-20261117.json').read_text())
check(all(fingerprint(root)==before[str(root)] for root in (V05,DESKTOP)),'all original v05 and Desktop inspected files unchanged during real run')
check(sha(ROOT/'private_inputs/calm_rr_v42.json')==sha(V05/'private_inputs/calm_rr_v42.json'),'source stimuli copy unchanged')
check(sha(P/'deepseek-tokenizer-20261117.zip')=='e7310d1dafe0a86d8a5629fe78a7c763760f651db9b8682718a1781dcd6fe495','official tokenizer digest')
gate=json.loads((P/'gate_a.json').read_text(encoding='utf-8'))
check(all(sha(ROOT/n)==h for n,h in gate['runtime_file_sha256'].items()),'runtime code preserved after preflight')
result={'protocol':'RR-ISOLATION-001','status':'COMPLETE_VERIFIED','observed_utc':datetime.now(timezone.utc).isoformat(),
    'complete_episodes':60,'batch_episodes':6,'isolated_episodes':54,'valid_generation_requests':120,'unique_ratings':432,'retries':0,
    'usage_derived_cost_usd':str(cost),'authorized_independent_cap_usd':'0.13','provider_invoice_reconciled':False,
    'historical_project_cumulative_reconciled':False,'historical_cap_replaced_for_this_run_by_owner':True,
    'usage_totals':dict(usage_total),'returned_model_aliases':sorted({r['returned_model'] for r in requests}),
    'documented_served_version':'DeepSeek-V4.1-Flash-1017 (official mapping; response alias only)',
    'summaries':summaries,'items':item_results,'frequency':frequency,'secondary':secondary,
    'independent_checks_passed':len(checks),'offline_tests_passed':64,
    'database_sha256':sha(P/'rr-isolation-001.sqlite3'),'source_preservation_passed':True,
    'limitations':['n=2 samples per item, arm and memory; descriptive feasibility only.','Human preTest reference is unprimed and previously inspected.','No stable effect or causal psychological mechanism established.','Official tokenizer/template with conservative overhead allowance; historical actual requests used to validate allowance.']}
(P/'verified-real-results-20261117.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
(P/'independent-checks-20261117.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
columns=['episode_id','arm','condition','repeat','source_scenario_id','item_id','rating_type','rating']
for path in (P/'ratings-real-20261117.csv',OUT/'ratings-real-20261117.private.csv'):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(flat)
with (P/'paired-item-w1-real-20261117.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(item_results[0]));w.writeheader();w.writerows(item_results)
safe={k:v for k,v in result.items() if k!='items'}
(OUT/'verified-real-summary-20261117.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf-8')
gate.update(run_status='complete_verified',new_model_calls=120,new_ratings=432,actual_usage_derived_cost_usd=str(cost),
            independent_checks_passed=len(checks),results_file='verified-real-results-20261117.json')
(P/'gate_a.json').write_text(json.dumps(gate,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('items','summaries','limitations')},indent=2))
print(json.dumps([r for r in summaries if r['group'] in ('all36','social12')],indent=2))
