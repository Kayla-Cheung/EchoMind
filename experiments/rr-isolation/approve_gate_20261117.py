"""Apply the owner's explicit 2026-11-17 authorization after independent preflight."""
import hashlib,json,os,sqlite3,sys,urllib.request,zipfile
from pathlib import Path
from decimal import Decimal
from datetime import datetime,timezone
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined
from tokenizers import Tokenizer
from rr_v05 import load_stimuli,load_human_reference,human_distribution
from isolation_protocol import schedule,messages,PARAMETERS,price_window
from journal import require_real_gate
from run_real import load_key

ROOT=Path(__file__).resolve().parent;P=ROOT/'private_exports'
OLD=ROOT.parent/'coordinator-resume-20261116'
sys.path.insert(0,str(OLD))
from independent_audit import fingerprint,V05,DESKTOP
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
AUTHFILE=Path(os.environ['ECHOMIND_AUTHFILE'])
cap=Decimal('.13');now=datetime.now(timezone.utc)
assert price_window(now)=='offpeak','Not in authorized off-peak window'
previous=json.loads(Path(os.environ['ECHOMIND_RR_MANIFEST']).read_text(encoding='utf-8'))
assert all(sha(V05/k)==v for k,v in previous['unchanged_sha256'].items()),'Frozen source mismatch'
audit=json.loads((OLD/'independent_audit.json').read_text(encoding='utf-8'))
assert sha(ROOT/'private_inputs/calm_rr_v42.json')==sha(V05/'private_inputs/calm_rr_v42.json')
stim=load_stimuli(ROOT/'private_inputs/calm_rr_v42.json')
human=Path(os.environ['ECHOMIND_HUMAN_CSV'])
assert sha(human)==audit['human_csv']['sha256']
assert sha(human.with_name('measures-v4.2.pdf'))=='76e6a0736f58d8b3bc36bf5fe811576b0d1a4400cffa32d1ceb2766ce20b91ae'
ref=human_distribution(load_human_reference(human,(V05/'private_inputs/split_salt.txt').read_text().strip(),.20))
assert ref==json.loads((P/'human_reference_aggregate.json').read_text())
archive=P/'deepseek-tokenizer-20261117.zip'
assert sha(archive)=='e7310d1dafe0a86d8a5629fe78a7c763760f651db9b8682718a1781dcd6fe495'
with zipfile.ZipFile(archive) as z:
    tok=Tokenizer.from_str(z.read('deepseek_v4_tokenizer/tokenizer.json').decode())
    cfg=json.loads(z.read('deepseek_v4_tokenizer/tokenizer_config.json'))
template=SandboxedEnvironment(undefined=StrictUndefined).from_string(cfg['chat_template'])
def tokens(msgs):return len(tok.encode(template.render(messages=msgs,bos_token=cfg['bos_token']['content'],add_generation_prompt=True),add_special_tokens=False).ids)
rows=[]
for c in schedule(stim):
    first=messages(stim,c,'encoding');second=messages(stim,c,'rating','')
    a=tokens(first)+256*len(first);b=tokens(second)+800+256*len(second)
    rows.append({'episode_id':c['episode_id'],'encoding':{'max_input_tokens':a,'max_output_tokens':800},
                 'rating':{'max_input_tokens':b,'max_output_tokens':1800}})
total_input=sum(r[p]['max_input_tokens'] for r in rows for p in ('encoding','rating'))
total_output=156000
bound=(Decimal(total_input)*Decimal('.15')+Decimal(total_output)*Decimal('.60'))/1000000
assert bound<=cap,'Whole matrix cannot fit authorized cap'

# Validate allowance against all 39 historical RR requests without printing prompts.
overages=[];ids=set()
for item in audit['databases']:
    path=Path(item['path']);wal=Path(str(path)+'-wal')
    assert not wal.exists() or wal.stat().st_size==0,'Historical WAL is active'
    assert sha(path)==item['sha256'],'Historical ledger changed'
    d=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
    for rid,raw,usage in d.execute('SELECT response_id,request_json,usage_json FROM requests'):
        ids.add(rid);msgs=json.loads(raw);u=json.loads(usage)
        overages.append({'extra_tokens':u['prompt_tokens']-tokens(msgs),'messages':len(msgs)})
    d.close()
assert len(ids)==39 and all(x['extra_tokens']<=256*x['messages'] for x in overages)
d=sqlite3.connect((P/'rr-isolation-001.sqlite3').as_uri()+'?mode=ro&immutable=1',uri=True)
assert d.execute('SELECT count(*) FROM requests').fetchone()[0]==0,'Requests already exist: inspect before launch'
assert d.execute("SELECT count(*) FROM episodes WHERE status='planned'").fetchone()[0]==60
d.close()

# Read-only provider checks; no generation or credential output.
key=load_key(AUTHFILE)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise RuntimeError('Unexpected provider redirect')
opener=urllib.request.build_opener(NoRedirect())
def read(path):
    req=urllib.request.Request('https://api.deepseek.com'+path,headers={'Authorization':'Bearer '+key})
    with opener.open(req,timeout=30) as r:return json.load(r)
models=read('/models')
assert any(m.get('id')=='deepseek-flash' for m in models.get('data',[])),'Fixed model unavailable'
balance=read('/user/balance')
usd=sum((Decimal(x['total_balance']) for x in balance.get('balance_infos',[]) if x.get('currency')=='USD'),Decimal(0))
cny=sum((Decimal(x['total_balance']) for x in balance.get('balance_infos',[]) if x.get('currency')=='CNY'),Decimal(0))
# 10 CNY/USD here is a deliberately conservative funding allowance, not a quoted FX rate.
funded=bool(balance.get('is_available')) and (usd>=cap or cny>=cap*10)
assert funded,'Available provider funds do not meet conservative whole-pilot allowance'

snapshot={str(root):fingerprint(root) for root in (V05,DESKTOP)}
(P/'preservation-before-real-20261117.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
authorization={'owner_selected_full_matrix':True,'owner_authorized_incremental_usd':'0.13','budget_scope':'independent_20261117',
    'owner_quote':'同意本轮独立新增≤0.13 USD，旧累计上限不适用本轮',
    'history_reconciliation_deferred_by_owner':True,'offpeak_only':True,'retries':0,'observed_utc':now.isoformat()}
(P/'owner-authorization-20261117.json').write_text(json.dumps(authorization,ensure_ascii=False,indent=2),encoding='utf-8')
old=json.loads((P/'gate_a.json').read_text(encoding='utf-8'))
(P/'gate-a-prior-20261116.json').write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
report={**old,**authorization,'observed_utc':datetime.now(timezone.utc).isoformat(),'decision':'GO','blockers':[],
    'run_status':'ready','approved_price_window':'offpeak','official_tokenizer_verified':True,'official_chat_template_verified':True,
    'exact_template_verified':False,'backend_template_identity_confirmed':False,'provider_billing_reconciled':False,
    'provider_auth_checked':True,'fixed_model_available':True,'available_funds_cover_cap':True,'readonly_provider_checks':2,
    'preflight_detail_file':'preflight-live-20261117.json','offline_tests_passed':64,
    'runtime_file_sha256':{n:sha(ROOT/n) for n in ('run_real.py','isolation_protocol.py','journal.py','rr_v05.py')},
    'cost':{'offpeak_diagnostic_usd':str(bound),'official_template_only_usd':'0.1082832','incremental_cap_usd':'0.13',
       'cumulative_cap_usd':None,'input_tokens_including_allowance':total_input,'max_output_tokens':total_output,
       'budget_basis':'Current official tokenizer and its supplied chat template; plus 256 input tokens per message; no cache hits; attempts=1',
       'historical_requests_validating_allowance':39,'maximum_historical_template_overage_tokens':max(x['extra_tokens'] for x in overages)},
    'checks':[{'label':'原始文件与同一人类 heldout 分布','state':'PASS'},{'label':'固定模型可用与余额检查','state':'PASS'},
       {'label':'官方分词器与全120请求预算（含开销余量）','state':'PASS'},{'label':'64项离线检查','state':'PASS'},
       {'label':'本轮独立新增上限','state':'0.13 USD'},{'label':'旧累计账单（按授权另行核对）','state':'UNRECONCILED'}],
    'implementation_status':'Reviewed bounded live sender enabled after explicit owner independent budget authorization; no retries.'}
require_real_gate(report)
(P/'preflight-live-20261117.json').write_text(json.dumps({'rows':rows,'whole_bound_usd':str(bound),'authorized_cap_usd':'0.13'},indent=2),encoding='utf-8')
(P/'gate_a.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'decision':'GO','whole_matrix_bound_usd':str(bound),'independent_cap_usd':'0.13','historical_allowance_check_requests':len(ids),
      'max_historical_overage_tokens':max(x['extra_tokens'] for x in overages),'provider_funds_sufficient':funded,'new_generation_calls':0},indent=2))
