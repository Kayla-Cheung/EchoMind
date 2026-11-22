"""RR-ISOLATION-001 message construction and offline preflight. No API transport."""
from __future__ import annotations
import hashlib, itertools, json, random, math,re
from collections import Counter
from decimal import Decimal
from datetime import datetime, timezone
from rr_v05 import SYSTEM_PROMPT, memory_messages, encoding_messages, rating_messages

PROTOCOL='RR-ISOLATION-001'
CONDITIONS=('none','neutral_direct','negative_direct')
PARAMETERS={'model':'deepseek-flash','temperature':0.7,'thinking':'disabled','attempts':1}
# Preserve historical ceilings until a reviewed protocol revision changes them.
OUTPUT_LIMITS={'encoding':800,'rating':1800}
INCREMENTAL_CAP=Decimal('.025');CUMULATIVE_CAP=Decimal('.050')
GRAMMAR_DIFF=[
 ('the following nine ambiguous stories independently and in order. Imagine yourself in each situation.',
  'the following ambiguous story. Imagine yourself in this situation.'),
 ('each comprehension question','the comprehension question'),
 ('keys are the story IDs','key is the story ID'),
 ('all 36 item IDs','all 4 item IDs'),
]

def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()

def schedule(stimuli,seed=20261116):
    cells=[]
    for c in CONDITIONS:
        for repeat in (1,2):
            for arm,items in [('BATCH',['all']),('ISOLATED',[s['id'] for s in stimuli['scenarios']])]:
                for scenario in items:
                    cell={'arm':arm,'condition':c,'repeat':repeat,'scenario_id':scenario}
                    cell['episode_id']='iso_'+digest({'protocol':PROTOCOL,**cell})[:24]
                    cells.append(cell)
    random.Random(seed).shuffle(cells)
    return [dict(x,order=i+1) for i,x in enumerate(cells)]

def select_stimuli(stimuli,cell):
    if cell['condition'] not in CONDITIONS or cell['arm'] not in ('BATCH','ISOLATED'):
        raise ValueError('Unknown arm/condition')
    chosen=stimuli['scenarios'] if cell['arm']=='BATCH' else [s for s in stimuli['scenarios'] if s['id']==cell['scenario_id']]
    if len(chosen)!=(9 if cell['arm']=='BATCH' else 1):raise ValueError('Incorrect scenario coverage')
    return dict(stimuli,scenarios=chosen)

def messages(stimuli,cell,phase,encoding_raw=None):
    if phase not in ('encoding','rating'):raise ValueError('Unknown phase')
    selected=select_stimuli(stimuli,cell)
    enc=encoding_messages(selected,cell['condition'])
    if cell['arm']=='ISOLATED':
        for before,after in GRAMMAR_DIFF[:3]:enc[-1]['content']=enc[-1]['content'].replace(before,after)
    if phase=='encoding':return enc
    if not isinstance(encoding_raw,str):raise ValueError('Rating requires this episode encoding response')
    tail=rating_messages(selected,cell['condition'],encoding_raw)[-2:]
    if cell['arm']=='ISOLATED':tail[-1]['content']=tail[-1]['content'].replace(*GRAMMAR_DIFF[3])
    return enc+tail

def strict_object(raw):
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('Duplicate JSON key')
            out[k]=v
        return out
    cleaned=raw.strip()
    if cleaned.startswith('```'):
        cleaned=re.sub(r'^```(?:json)?\s*|\s*```$','',cleaned,flags=re.I|re.S)
    value=json.loads(cleaned,object_pairs_hook=unique)
    if not isinstance(value,dict):raise ValueError('Expected JSON object')
    return value

def parse(raw,stimuli,cell,phase):
    v=strict_object(raw);s=select_stimuli(stimuli,cell)
    keys={x['id'] for x in s['scenarios']} if phase=='encoding' else {e['item_id'] for x in s['scenarios'] for e in x['interpretations']}
    if set(v)!=keys:raise ValueError('Missing or extra response keys')
    if phase=='encoding':
        if any(not isinstance(x,str) or x.lower() not in ('yes','no') for x in v.values()):raise ValueError('Expected Yes/No')
    elif phase=='rating':
        if any(type(x) is not int or x not in (1,2,3,4) for x in v.values()):raise ValueError('Expected integer 1–4')
    else:raise ValueError('Unknown phase')
    return v

def price_window(now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('Timezone-aware UTC timestamp required')
    now=now.astimezone(timezone.utc)
    peak=now.weekday()<5 and (1<=now.hour<4 or 6<=now.hour<10)
    return 'peak' if peak else 'offpeak'

def token_count(tokenizer,msgs,overhead=10):
    # Diagnostic only: this overhead is not an exact served chat-template proof.
    return overhead+sum(len(tokenizer.encode(m['content']).ids)+overhead for m in msgs)

def preflight(stimuli,tokenizer,limits=None,overhead=10):
    limits=limits or {a:OUTPUT_LIMITS for a in ('BATCH','ISOLATED')}
    inputs=outputs=0;rows=[]
    for cell in schedule(stimuli):
        lim=limits[cell['arm']]
        i=token_count(tokenizer,messages(stimuli,cell,'encoding'),overhead)+token_count(tokenizer,messages(stimuli,cell,'rating',''),overhead)+lim['encoding']
        o=lim['encoding']+lim['rating'];inputs+=i;outputs+=o
        rows.append({'episode_id':cell['episode_id'],'max_input_tokens':i,'max_output_tokens':o})
    off=(Decimal(inputs)*Decimal('.15')+Decimal(outputs)*Decimal('.60'))/1000000
    output_only=Decimal(outputs)*Decimal('.60')/1000000
    return {'episodes':60,'calls':120,'ratings_if_complete':432,'input_tokens':inputs,'output_tokens':outputs,
            'limits':limits,'offpeak_diagnostic_usd':str(off),'peak_diagnostic_usd':str(off*2),
            'output_only_offpeak_upper_budget_usd':str(output_only),'incremental_cap_usd':str(INCREMENTAL_CAP),
            'cumulative_cap_usd':str(CUMULATIVE_CAP),'fits_incremental':off<=INCREMENTAL_CAP,
            'exact_template_verified':False,'overhead_assumption':f'{overhead} tokens/message + {overhead}/request',
            'cache_hits_assumed':0,'attempts':1,'rows':rows}

def w1(a,b):
    if len(a)!=4 or len(b)!=4 or abs(sum(a)-1)>1e-9 or abs(sum(b)-1)>1e-9:raise ValueError('Invalid probability vectors')
    return sum(abs(sum(a[:k])-sum(b[:k])) for k in (1,2,3))

def analyze(rows,human,stimuli):
    """Require balanced full matrix; never compare a selected subset silently."""
    expected={(c['arm'],c['condition'],c['repeat'],e['item_id']) for c in schedule(stimuli)
              for s in select_stimuli(stimuli,c)['scenarios'] for e in s['interpretations']}
    keys=[(r['arm'],r['condition'],r['repeat'],r['item_id']) for r in rows]
    if len(keys)!=432 or len(set(keys))!=432 or set(keys)!=expected:raise ValueError('Incomplete/unbalanced or duplicate matrix')
    if any(type(r['rating']) is not int or r['rating'] not in (1,2,3,4) for r in rows):raise ValueError('Illegal rating')
    mapping={e['item_id']:(s,e) for s in stimuli['scenarios'] for e in s['interpretations']}
    items=[]
    for condition in CONDITIONS:
        for item_id,(s,e) in mapping.items():
            ref=human[f"{s['id']}_{e['type']}"]
            if not ref['n']:raise ValueError('Missing human marginal')
            cell={'condition':condition,'item_id':item_id,'scenario_id':s['id'],'category':s['category'],'type':e['type']}
            for arm in ('BATCH','ISOLATED'):
                vals=[r['rating'] for r in rows if r['arm']==arm and r['condition']==condition and r['item_id']==item_id]
                dist=[vals.count(i)/2 for i in (1,2,3,4)]
                cell[arm]=w1(dist,[ref['probabilities'][str(i)] for i in (1,2,3,4)])
                cell[arm+'_agreement']=vals[0]==vals[1]
                cell[arm+'_variance']=sum((x-sum(vals)/2)**2 for x in vals)/2
            cell['isolated_minus_batch']=cell['ISOLATED']-cell['BATCH'];items.append(cell)
    summaries=[]
    for c in CONDITIONS:
        for group in ('all36','social12',*[s['id'] for s in stimuli['scenarios']]):
            subset=[x for x in items if x['condition']==c and (group=='all36' or group=='social12' and x['category']=='social' or x['scenario_id']==group)]
            summaries.append({'condition':c,'group':group,'items':len(subset),**{k:sum(x[k] for x in subset)/len(subset) for k in ('BATCH','ISOLATED','isolated_minus_batch')}})
    frequency={a:{c:{str(i):sum(r['arm']==a and r['condition']==c and r['rating']==i for r in rows) for i in (1,2,3,4)} for c in CONDITIONS} for a in ('BATCH','ISOLATED')}
    return {'items':items,'summaries':summaries,'frequency':frequency,'n_per_item_per_arm_condition':2,
            'limitations':['Descriptive feasibility pilot; n=2 per item.','Previously inspected human heldout; not confirmatory.','Memory conditions align to unprimed human reference.','Packetization confounds task size, context length and cross-story context.']}
