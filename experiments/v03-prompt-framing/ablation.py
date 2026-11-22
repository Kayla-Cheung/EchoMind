"""Exploratory factorial pilot: response format x provenance of memory material.

No 'anxiety level' is manipulated or inferred. Do not mix with memory-ratio-v1.
"""
import copy
from collections import Counter

from mechanism import wilson
from state_protocol import fingerprint, scenario_hash, validate_protocol, VARIANTS

PROTOCOL_ID = 'memory-ablation-v1'
MEMORY_GROUPS = ('positive_self', 'negative_self', 'negative_other', 'baseline')
FORMATS = ('channels', 'free')
LABELS = {
    'positive_self': '自己的平稳经历',
    'negative_self': '自己的不利经历',
    'negative_other': '他人的不利经历',
    'baseline': '不提供经历',
}
FORMAT_LABELS = {'channels': '三通道', 'free': '自由叙述'}
CODER_VERSION = 'blind-ablation-v2.0'
SCORING_NOTE = ('严格负面归因：明确把对方意图、态度或当前结果解释为不利；'
                '仅有“又是”、失落、担忧、反复查看不自动算作负面归因。'
                '明确等待与明确终止未来接触分开；心里想回避不等同于已采取或明确决定的行动。')


def build_ablation_tasks(design, request, models, repeats, config):
    validate_protocol(config, design)
    conditions = request.get('conditions', list(MEMORY_GROUPS))
    formats = request.get('formats', list(FORMATS))
    scenario_ids = request.get('scenario_ids', ['S01'])
    variants = request.get('variants', ['A'])
    if (not isinstance(conditions, list) or set(conditions) != set(MEMORY_GROUPS)
            or len(conditions) != len(MEMORY_GROUPS)):
        raise ValueError('消融实验必须包含四组记忆来源条件')
    if not isinstance(formats, list) or set(formats) != set(FORMATS) or len(formats) != len(FORMATS):
        raise ValueError('消融实验必须同时包含三通道和自由叙述')
    scenes = {s['id']: s for s in config['scenarios']}
    if not isinstance(scenario_ids, list) or len(scenario_ids) != 1 or scenario_ids[0] not in scenes:
        raise ValueError('消融实验每批固定一个情境')
    if not isinstance(variants, list) or len(variants) != 1 or variants[0] not in VARIANTS:
        raise ValueError('消融实验每批固定一个 A/B/C 材料版')
    if len(models) != 1:
        raise ValueError('消融实验每批只能运行一个角色模型')
    variant, scene = variants[0], scenes[scenario_ids[0]]
    profiles = {p['id']: p for p in config['profiles']}
    texts = {
        'positive_self': profiles['state_none']['memories'][variant],
        'negative_self': profiles['state_moderate']['memories'][variant],
        'negative_other': profiles['state_moderate']['memories'][variant],
        'baseline': [],
    }
    source = {'positive_self':'self', 'negative_self':'self', 'negative_other':'other', 'baseline':'none'}
    design_hash = fingerprint({k: design[k] for k in ('identity', 'system_prompt', 'coding_rules')})
    return [
        {'condition': c, 'scenario': copy.deepcopy(scene), 'repeat': r, 'model_spec': models[0],
         'memories': [{'id': f'{variant}-{i+1}', 'text': text, 'synthetic': True}
                      for i, text in enumerate(texts[c])],
         'ablation_format': fmt, 'memory_source': source[c],
         'state_meta': {'induction_variant': variant, 'scenario_split': scene['split'],
                        'scenario_hash': scenario_hash(scene), 'protocol_hash': fingerprint(config),
                        'design_hash': design_hash},
        }
        for fmt in formats for c in conditions for r in range(1, repeats + 1)
    ]


def ablation_batches(records):
    batches = {}
    for row in records:
        if row.get('protocol') != PROTOCOL_ID:
            continue
        bid = row['batch_id']
        if bid not in batches:
            batches[bid] = {'id':bid, 'timestamp':row['timestamp'], 'model':row['model'],
                            'source':row['source'], 'n':0}
        batches[bid]['n'] += 1
    return sorted(batches.values(), key=lambda x:x['timestamp'], reverse=True)


def summarize_ablation(records, batch_id):
    rows = sorted((r for r in records if r.get('protocol') == PROTOCOL_ID and r.get('batch_id') == batch_id),
                  key=lambda x:x.get('schedule_index', 0))
    if not rows:
        raise ValueError('没有对应的消融实验记录')
    first = rows[0]
    repeats = first.get('snapshot', {}).get('request', {}).get('repeats')
    cells = {}
    for fmt in FORMATS:
        for condition in MEMORY_GROUPS:
            subset = [r for r in rows if r.get('ablation_format') == fmt and r.get('condition') == condition]
            complete = [r for r in subset if r.get('status') == 'complete']
            inter = Counter(r['machine_coding']['interpretation'] for r in complete)
            acts = Counter(r['machine_coding']['action'] for r in complete)
            n = len(complete)
            cells[f'{fmt}:{condition}'] = {'format':fmt, 'condition':condition, 'n':n,
                'recorded':len(subset), 'failed':sum(r.get('status') == 'error' for r in subset),
                'interpretations':dict(inter), 'actions':dict(acts),
                'negative_rate':inter['negative']/n if n else None,
                'avoid_rate':acts['avoid']/n if n else None,
                'negative_ci':wilson(inter['negative'], n),
                'repetition_rate':(sum('又是' in (r.get('narrative') or '') or '果然又' in (r.get('narrative') or '') for r in complete)/n if n else None)}
    def rate(fmt, c):
        return cells[f'{fmt}:{c}']['negative_rate']
    def diff(x, y):
        return x - y if x is not None and y is not None else None
    contrasts = {}
    for fmt in FORMATS:
        contrasts[fmt] = {
            'negative_vs_positive':diff(rate(fmt,'negative_self'), rate(fmt,'positive_self')),
            'self_vs_other_negative':diff(rate(fmt,'negative_self'), rate(fmt,'negative_other')),
            'negative_vs_baseline':diff(rate(fmt,'negative_self'), rate(fmt,'baseline')),
        }
    interaction = diff(contrasts['channels']['negative_vs_positive'], contrasts['free']['negative_vs_positive'])
    config_fields = ('source','model_spec','evaluator_spec','scenario_hash', 'induction_variant',
                     'protocol_hash','design_hash','coder_version')
    blockers = []
    if type(repeats) is not int or not 1 <= repeats <= 100 or len(rows) != 8*repeats:
        blockers.append('记录总量与本批计划不符')
    for field in config_fields:
        if len({fingerprint(r.get(field)) for r in rows}) != 1:
            blockers.append('同批次不一致：'+field)
    if any(r.get('coder_version') != CODER_VERSION for r in rows):
        blockers.append('编码规则版本不一致')
    if any(c['n'] != repeats or c['recorded'] != repeats for c in cells.values()):
        blockers.append('部分试次失败、取消或缺失')
    for fmt in FORMATS:
        for cond in MEMORY_GROUPS:
            selected = [r for r in rows if r.get('ablation_format') == fmt and r.get('condition') == cond]
            if sorted(r.get('repeat') for r in selected) != list(range(1,repeats+1)):
                blockers.append(f'{fmt}/{cond} 重复编号异常')
            if len({r.get('prompt_hash') for r in selected}) != 1:
                blockers.append(f'{fmt}/{cond} 提示词不一致')
    return {'batch_id':batch_id, 'source':first['source'], 'model':first['model'],
        'scenario':first['snapshot']['scenario'], 'variant':first['induction_variant'], 'repeats':repeats,
        'planned_n':8*repeats if isinstance(repeats,int) else None,
        'complete_n':sum(c['n'] for c in cells.values()), 'cells':cells,
        'contrasts':contrasts, 'format_interaction_descriptive':interaction,
        'status':'mock' if first['source'] != 'LIVE_LLM_API' else 'incomplete' if blockers else 'descriptive',
        'blockers':list(dict.fromkeys(blockers)), 'records':rows,
        'notice':('本页面仅做探索性差值，不进行显著性或焦虑模拟成功判定。'
                  '自由叙述与三通道都由相同编码规则 v2 评分，但需要对条件盲的人工复核；'
                  '重复生成不代表独立人类被试。')}
