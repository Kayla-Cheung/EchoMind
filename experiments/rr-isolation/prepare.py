"""Create a private plan and inspect Gate A. This command cannot send model requests."""
import argparse,hashlib,importlib.util,json,sys,zipfile,sqlite3
from pathlib import Path
from datetime import datetime,timezone
from tokenizers import Tokenizer
from rr_v05 import load_stimuli,load_human_reference,human_distribution
from isolation_protocol import PARAMETERS,PROTOCOL,preflight,GRAMMAR_DIFF,messages,schedule,canonical
from journal import create,require_real_gate,status

ROOT=Path(__file__).resolve().parent
AUDIT=ROOT.parent/'coordinator-resume-20261116'
V05=Path(r'C:\Users\Kayla\Documents\Codex\2026-11-14\referenced-chatgpt-conversation-this-is-an\work\EchoMind-v05-human-rr')
HUMAN=Path(r'C:\Users\Kayla\Documents\Codex\2026-10-28\referenced-chatgpt-conversation-this-is-an-3\work\open-benchmark-discovery-20261030\calm\rr.csv')
DB=ROOT/'private_exports/rr-isolation-001.sqlite3'

def filehash(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def prepare():
    stim=load_stimuli(ROOT/'private_inputs/calm_rr_v42.json')
    a=json.loads((AUDIT/'independent_audit.json').read_text(encoding='utf-8'))
    legacy=json.loads((AUDIT/'legacy_cost_audit.json').read_text(encoding='utf-8'))
    tokpath=Path(a['tokenizer']['path'])
    with zipfile.ZipFile(tokpath) as z:tok=Tokenizer.from_str(z.read('deepseek_v4_tokenizer/tokenizer.json').decode())
    costs=preflight(stim,tok)
    # Private salt stays in memory only. No participant-level exports are created.
    humans=load_human_reference(HUMAN,(V05/'private_inputs/split_salt.txt').read_text().strip(),.20)
    ref=human_distribution(humans)
    prior=V05/'data/human-rr-v05.sqlite3'
    d=sqlite3.connect(prior.as_uri()+'?mode=ro&immutable=1',uri=True)
    saved={r[0]:{'n':r[1],'probabilities':json.loads(r[2])} for r in d.execute("SELECT human_column,n,distribution_json FROM human_reference WHERE batch_id='rrv05_20261114T103014Z_69ca2c7d' AND split='heldout'")};d.close()
    human_match=ref==saved
    if not human_match:raise RuntimeError('Human heldout reference mismatch')
    if filehash(HUMAN)!=a['human_csv']['sha256']:raise RuntimeError('Human file changed')
    previous=json.loads(Path(r'C:\Users\Kayla\Documents\Codex\RR-ISOLATION-001\coordinator-20261116\verification_manifest.json').read_text(encoding='utf-8'))
    if not all(filehash(V05/name)==value for name,value in previous['unchanged_sha256'].items()):raise RuntimeError('Frozen file mismatch')
    if not DB.exists():create(DB,stim)
    stats=status(DB)
    output_examples=[]
    for arm in ('BATCH','ISOLATED'):
        sample=next(c for c in schedule(stim) if c['arm']==arm and c['condition']=='none')
        output_examples.append({'arm':arm,'encoding_limits':800,'rating_limits':1800})
    report={
       'protocol':PROTOCOL,'execution_owner':'Work','observed_utc':datetime.now(timezone.utc).isoformat(),
       'decision':'NO-GO','new_model_calls':stats['counts']['requests'],'new_ratings':stats['counts']['ratings'],
       'planned_episodes':60,'planned_calls':120,'planned_ratings':432,'parameters':PARAMETERS,
       'cost':{k:v for k,v in costs.items() if k!='rows'},'exact_template_verified':False,'provider_billing_reconciled':False,
       'source_hashes_match_previous':True,'human_reference_match':human_match,
       'history':{'v05_requests':15,'v05_ratings':252,'v05_peak_conservative_usd':'0.007544064',
          'valence_requests':24,'valence_ratings':432,'valence_offpeak_usage_usd':'0.004648758',
          'v05_plus_valence_mixed_conservative_usd':'0.012192822',
          'legacy_distinct_deepseek_responses':legacy['distinct_deepseek_response_ids'],
          'legacy_deduplicated_recorded_job_cost_usd':str(round(float(legacy['unique_recorded_job_cost_usd']),9)),
          'legacy_current_offpeak_equivalent_usd':legacy['current_offpeak_rate_equivalent_usd'],
          'billing_caveat':'账本和按用量推算的费用，不等于供应商实际账单；旧批次不能直接相加为本次授权范围。'},
       'blockers':[
          {'id':'cost','title':'完整矩阵的费用上界超过增量上限','detail':'保留原输出额度（编码 800、评分 1800）：仅输出额度对应的最坏预算已达 $0.093600；含输入的诊断估算约 $0.109。上限仍为 $0.025。'},
          {'id':'cumulative','title':'全项目累计费用尚未核清','detail':'v0.5 与 Prompt-Valence 小计 $0.012192822；更早账本还存在去重后的历史费用记录 $0.0690516。必须核清授权范围、历史价格及实际账单，不能假定全部累计只有前者。'},
          {'id':'tokenizer','title':'精确聊天模板与当前分词器对应关系待核验','detail':'已使用本地 DeepSeek v4 分词器；额外 10 token／消息为诊断假设，不能宣称完整精确上界。'}],
       'checks':[{'label':'原始五项文件指纹','state':'PASS'},{'label':'同一人类 heldout 分布重算','state':'PASS'},
          {'label':'60 对话／120 请求／432 评分的设计','state':'PASS'},
          {'label':'新真实调用','state':'0'},{'label':'完整增量预算','state':'NO-GO'},{'label':'累计账单','state':'UNRECONCILED'}],
       'price_url':'https://api-docs.deepseek.com/quick_start/pricing/',
       'tokenizer_url':'https://api-docs.deepseek.com/quick_start/token_usage/',
       'limitations':['每个条件、每题、每组只有 2 次模型样本；仅作描述性可行性试验。',
          '评分为语义相似度，不是信念、乐观程度或人类情绪。','人类 preTest 未注入记忆；heldout 之前已查看，不是新的确证性测试集。',
          '分包同时改变上下文长度、任务大小和跨故事背景，不能归因于单一心理机制。'],
       'implementation_status':'Offline workbench and journal verified separately. No live transport activated.',
       'grammar_diff':GRAMMAR_DIFF}
    private=ROOT/'private_exports';private.mkdir(exist_ok=True)
    (private/'gate_a.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (private/'human_reference_aggregate.json').write_text(json.dumps(ref,indent=2),encoding='utf-8')
    (private/'preflight_detailed.json').write_text(json.dumps(costs,indent=2),encoding='utf-8')
    provenance={'frozen_pr':'https://github.com/Kayla-Cheung/EchoMind/pull/7','commit':'8345b91ef8de084145ba2f9d5f36122f412de04a',
       'rr_v05_sha256':filehash(ROOT/'rr_v05.py'),'original_source_root':str(V05),
       'stimulus_file_sha256':filehash(ROOT/'private_inputs/calm_rr_v42.json'),'tokenizer_sha256':filehash(tokpath),
       'human_csv_sha256':filehash(HUMAN),'source_manifest_sha256':filehash(ROOT/'data/rr_v05_source_manifest.json')}
    (private/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--real',action='store_true');args=p.parse_args()
    if args.real:
        report=json.loads((ROOT/'private_exports/gate_a.json').read_text(encoding='utf-8'))
        require_real_gate(report)
        raise SystemExit('No reviewed live transport installed. Stop before transmission.')
    report=prepare()
    print(json.dumps({'decision':report['decision'],'counts':status(DB)['counts'],'offpeak_diagnostic_usd':report['cost']['offpeak_diagnostic_usd'],'new_model_calls':report['new_model_calls']},indent=2))
