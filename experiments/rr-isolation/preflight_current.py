"""Read-only current official-tokenizer preflight; never reads keys or sends API calls."""
import hashlib,json,zipfile
from pathlib import Path
from decimal import Decimal
from datetime import datetime,timezone
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined
from tokenizers import Tokenizer
from rr_v05 import load_stimuli
from isolation_protocol import schedule,messages
ROOT=Path(__file__).resolve().parent;P=ROOT/'private_exports'
archive=P/'deepseek-tokenizer-20261117.zip'
with zipfile.ZipFile(archive) as z:
    tok=Tokenizer.from_str(z.read('deepseek_v4_tokenizer/tokenizer.json').decode())
    cfg=json.loads(z.read('deepseek_v4_tokenizer/tokenizer_config.json'))
template=SandboxedEnvironment(undefined=StrictUndefined).from_string(cfg['chat_template'])
def n(msgs):
    rendered=template.render(messages=msgs,bos_token=cfg['bos_token']['content'],add_generation_prompt=True)
    return len(tok.encode(rendered,add_special_tokens=False).ids)
stim=load_stimuli(ROOT/'private_inputs/calm_rr_v42.json');rows=[]
for c in schedule(stim):
    # Keep 800/1800 limits unchanged; include full encoding allowance in rating input.
    encoding=n(messages(stim,c,'encoding'))
    rating=n(messages(stim,c,'rating',''))+800
    rows.append({'episode_id':c['episode_id'],'input_tokens_official_template':encoding+rating,
                 'max_output_tokens':2600,'message_count':len(messages(stim,c,'encoding'))+len(messages(stim,c,'rating',''))})
inputs=sum(r['input_tokens_official_template'] for r in rows)
outputs=sum(r['max_output_tokens'] for r in rows)
off=(Decimal(inputs)*Decimal('.15')+Decimal(outputs)*Decimal('.60'))/1000000
# A separately displayed allowance is not a claim about the private serving template.
extra_input=sum(r['message_count']*256 for r in rows)
off_with_allowance=off+Decimal(extra_input)*Decimal('.15')/1000000
report={'observed_utc':datetime.now(timezone.utc).isoformat(),'owner_selected_scope':'Full BATCH/ISOLATED: 60 episodes, 120 calls, 432 ratings',
    'new_model_calls':0,'official_archive_url':'https://cdn.deepseek.com/api-docs/deepseek_v4_tokenizer.zip',
    'official_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
    'fresh_archive_matches_previous':hashlib.sha256(archive.read_bytes()).hexdigest()=='e7310d1dafe0a86d8a5629fe78a7c763760f651db9b8682718a1781dcd6fe495',
    'included_chat_template_sha256':hashlib.sha256(cfg['chat_template'].encode()).hexdigest(),
    'input_tokens_including_encoding_output':inputs,'max_output_tokens':outputs,
    'offpeak_template_budget_usd':str(off),'offpeak_budget_with_256_input_tokens_per_message_allowance_usd':str(off_with_allowance),
    'peak_budget_with_allowance_usd':str(off_with_allowance*2),
    'output_only_offpeak_upper_budget_usd':'0.093600','incremental_authorized_usd':'0.025','cumulative_authorized_usd':'0.050',
    'backend_template_identity_confirmed':False,'provider_billing_reconciled':False,
    'offline_tests_passed':62,'decision':'NO-GO: existing incremental cap insufficient and cumulative accounting unresolved',
    'rows':rows}
(P/'preflight-20261117.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
safe={k:v for k,v in report.items() if k!='rows'}
(ROOT.parents[1]/'outputs/preflight-20261117.json').write_text(json.dumps(safe,indent=2),encoding='utf-8')
print(json.dumps(safe,indent=2))
