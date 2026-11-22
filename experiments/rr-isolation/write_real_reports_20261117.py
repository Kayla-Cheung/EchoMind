import hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parent;P=ROOT/'private_exports';OUT=ROOT.parents[1]/'outputs'
r=json.loads((P/'verified-real-results-20261117.json').read_text(encoding='utf-8'))
g=json.loads((P/'gate_a.json').read_text(encoding='utf-8'))
approved=dict(g)
for name in ('actual_usage_derived_cost_usd','independent_checks_passed','results_file'):approved.pop(name,None)
approved.update(run_status='ready',new_model_calls=0,new_ratings=0)
db=sqlite3.connect((P/'rr-isolation-001.sqlite3').as_uri()+'?mode=ro&immutable=1',uri=True)
runmeta=json.loads(db.execute("SELECT value FROM meta WHERE key='real_run'").fetchone()[0]);db.close()
serialized=json.dumps(approved,ensure_ascii=False,sort_keys=True,separators=(',',':'))
assert hashlib.sha256(serialized.encode()).hexdigest()==runmeta['gate_hash']
(P/'gate-a-approved-20261117.json').write_text(json.dumps(approved,ensure_ascii=False,indent=2),encoding='utf-8')
names={'none':'无记忆','neutral_direct':'中性记忆','negative_direct':'负面记忆'}
lines=['# RR-ISOLATION-001：完整真实对照结果','',
 '2026-11-17（Asia/Shanghai）','',
 '**完成且独立核验通过：60 个独立对话、120 次有效真实生成调用、432 条唯一合法评分；0 次重试。**','',
 '网页工作台：http://127.0.0.1:8782/ ，选择「真实结果」查看。','',
 '## 运行与预算','',
 '- Batch：6 个对话；Isolated：54 个对话。每个对话包含编码和评分两个阶段。',
 '- 固定 deepseek-flash、P0、temperature=0.7、关闭推理模式，原始九个故事与 36 个选项保持不变。',
 '- 你明确授权本轮独立新增上限 **0.13 USD**，原累计 0.050 USD 不约束本轮；历史累计账单仍未核清，未被改写成“已核清”。',
 '- 执行前完整保守预算（官方分词器／模板，加每条消息 256 个输入 token 余量，编码回答带入第二阶段，不假设缓存命中）为 **0.1251792 USD**。',
 f'- 本轮按 API 返回 usage 与非高峰费率独立核算费用：**{r["usage_derived_cost_usd"]} USD**。这是用量核算值，不是供应商最终账单核对。',
 '- 实际输入 50,932 token，其中缓存命中 25,088；实际输出 4,851 token。所有请求均处于核实的非高峰时窗。',
 '- 返回的模型别名全部为 deepseek-flash。官方当日映射为 DeepSeek-V4.1-Flash-1017；响应没有提供更细的版本身份，未将别名当作独立版本证明。','',
 '## 同题配对 W1','',
 'W1 越低，越接近同一批人类 preTest 题目的边际分布。以下差值为 Isolated − Batch；负数表示本次 Isolated 较近。每个题目、每种记忆、每组只有 2 个模型评分。','',
 '全部 36 题：','']
for x in r['summaries']:
 if x['group']=='all36':lines.append(f'- {names[x["condition"]]}：Batch **{x["BATCH"]:.4f}**；Isolated **{x["ISOLATED"]:.4f}**；差值 **{x["isolated_minus_batch"]:+.4f}**。')
lines+=['','社交情境全部 12 题（包含目标与干扰选项，不能直接与旧报告的社交目标 6 题均值混用）：','']
for x in r['summaries']:
 if x['group']=='social12':lines.append(f'- {names[x["condition"]]}：Batch **{x["BATCH"]:.4f}**；Isolated **{x["ISOLATED"]:.4f}**；差值 **{x["isolated_minus_batch"]:+.4f}**。')
lines+=['','这次没有出现“Isolated 在所有记忆条件下都更接近人类”的一致模式。无记忆的全 36 题均值下降，但中性和负面记忆均值上升；社交 12 题三种记忆条件下均上升。','',
 '## 评分尺度与重复性','']
for arm in ('BATCH','ISOLATED'):
 counts=[sum(c[str(i)] for c in r['frequency'][arm].values()) for i in (1,2,3,4)]
 lines.append(f'- {arm}（216 条）：1／2／3／4 分频数为 **'+ '／'.join(map(str,counts))+'**。')
lines+=['','Isolated 出现了 9 条 4 分，Batch 没有 4 分。出现更广的评分范围不等于更接近人类分布。','',
 '两次重复对同一题的评分一致率：','']
for x in r['secondary']:lines.append(f'- {x["arm"]}／{names[x["condition"]]}：**{x["item_repetition_agreement"]:.1%}**；平均题内总体方差 {x["mean_within_item_population_variance"]:.4f}；社交目标平均 ps−ns = {x["social_mean_ps_minus_ns"]:+.4f}。')
lines+=['','## 每个情境的结果','',
 '以下各情境均包含原始 4 个选项；保留正负差值，不筛选结果：','']
for x in r['summaries']:
 if x['group'] not in ('all36','social12'):lines.append(f'- {names[x["condition"]]}／{x["group"]}：Batch {x["BATCH"]:.4f}，Isolated {x["ISOLATED"]:.4f}，差值 {x["isolated_minus_batch"]:+.4f}。')
lines+=['','## 核验与资料保留','',
 f'- **{r["independent_checks_passed"]} 项独立只读核验通过**，并完成 64 项离线回归检查。',
 '- 核对完整平衡覆盖、原先保存的私有消息模板、每阶段提示哈希、120 个不同响应身份、无历史响应复用、每阶段一次尝试及用量成本。',
 '- 108 个“记忆×题目”的配对 W1 用独立累计分布算法重新计算，与网页算法逐项一致，误差小于 1e-12。',
 '- 原始 v0.5 与 Desktop 目录在本轮前后的所有已指纹文件保持一致；源刺激、人类参考和同一划分没有变更。',
 '- 原始消息、响应、SQLite、私有模板和完整逐题分析保留在本地私有导出目录；未推送代码、合并或上传这些资料。',
 '- 同目录的 ratings-real-20261117.private.csv 为 432 条模型评分，不包含人类参与者行或原始题目全文。','',
 '## 解释限制','',
 '- 每题每条件每组仅 n=2，不能可靠估计完整响应分布或稳定效应；432 条评分不等于 432 名独立参与者。',
 '- 人类 preTest 没有注入记忆；记忆条件下的 W1 只是对未 priming 参考的描述性对齐。',
 '- 此 heldout 先前已用于查看方法效果，不是新的确证性测试集；没有根据本轮结果再次调提示或追加调用。',
 '- 分包同时改变跨故事背景、任务大小、输入长度及输出规模，不能将差异归因于单一心理机制。',
 '- 1–4 分衡量语义相似度，不直接衡量信念、情绪或心理乐观。','',
 '依据：[DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/)、[官方分词说明](https://api-docs.deepseek.com/quick_start/token_usage/)、[研究规格 Issue #12](https://github.com/Kayla-Cheung/EchoMind/issues/12)。','']
text='\n'.join(lines)
for path in (OUT/'04_RESULTS_REAL_20261117.md',P/'04_RESULTS_REAL_20261117.md'):path.write_text(text,encoding='utf-8')
next_text='''# RR-ISOLATION-001：下一步决定

完整真实可行性对照已结束，停止继续调用模型。本轮没有追加实验或调优授权。

- 保留全部逐题正负差值。当前结果没有支持“单情境隔离普遍更接近人类”的一致结论。
- 若后续增加重复次数，应先确定唯一主要比较范围、样本量与新预算，再另行授权，不能把 n=2 的波动当作稳定效应。
- 继续区分社交全部 12 题与社交目标 6 题；不能把不同题目集合的 W1 当作同一个指标比较。
- 不依据这次已经查看的人类 heldout 再次搜索提示词；若进行方法选择，后续确证需要独立资料。
- 历史全项目费用核对仍待完成。本轮使用独立 0.13 USD 授权，不能据此把旧账标记为已核清。
'''
for path in (OUT/'05_NEXT_DECISION_REAL_20261117.md',P/'05_NEXT_DECISION_REAL_20261117.md'):path.write_text(next_text,encoding='utf-8')
method={'protocol':'RR-ISOLATION-001','schedule_seed':20261116,'design':'3 memories x 2 arms x 2 repeats, with 9 independent scenario episodes per isolated cell',
        'parameters':runmeta['parameters'],'immutable_gate_hash':runmeta['gate_hash'],'validated_gate_checkpoint_digest':True,
        'budget_authorization':json.loads((P/'owner-authorization-20261117.json').read_text(encoding='utf-8')),
        'source_version':'PR #7 8345b91ef8de084145ba2f9d5f36122f412de04a; P0, memory, encoding/rating construction preserved',
        'grammar_diff':g['grammar_diff'],'attempts_per_stage':1,'time_window':'offpeak only','retry_policy':'stop on invalid or ambiguous, never auto retry',
        'primary_comparison':'108 paired memory x item W1 entries, report 36 all-items and 12 social-items separately per memory',
        'human_reference':'same unprimed preTest heldout marginals, previously inspected; no confirmatory claims'}
(P/'03_EXPERIMENT_METHOD_REAL_20261117.json').write_text(json.dumps(method,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved reports, method, and immutable approved Gate A checkpoint.')
