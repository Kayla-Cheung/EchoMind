# EchoMind Demo 2 · Context Injection MVP

本实验现作为独立 EchoMind 项目维护，根目录 `C:\Users\Kayla\Desktop\EchoMind`。代码、数据库、备份和导出均在该目录内；运行不依赖 SOS 文件夹，也不使用 SOS 的数据库／离线环境变量。历史协议和旧记录保留原始标识以供追溯。

协议 `memory_acquisition_v02`；独立于旧协议。角色为现有配置中的林知，20 岁、普通大学生。每批冻结身份及全部材料，不增加人格或临床标签。

研究问题：只检验不同 context injection 策略对同一 LLM 在受控模糊社交情境中公开输出的影响。另设一个非社交情境观察任务边界。框架为固定身份与决策模型 → 构造输入前缀 → 冻结输入快照 → 独立情境 → 公开回应 → 独立请求编码 → 逐情境描述。

这里的“记忆”和数据库字段名是兼容旧实现的材料称呼。Snapshot 是可重放的消息输入，不是模型内持久记忆；不要求形成心智状态、产生主观经历感或进行多 Agent 模拟。陈晨、许宁的台词全部由程序固定，不能自主行动；Interactive 中只有同一决策模型生成两句回应。Coder 是另一次测量请求，可使用同型号模型，不代表另一个参与社交的 Agent，也不保证测量误差独立。

2026-10-27 审查修订：Gate 版本 `context-injection-audit-v0.2.1` 加入冻结配置。实验事实、情境、公开输出 Prompt、编码类别均未改变；新增定位与安全元数据会改变 protocol_hash，旧 MOCK 和历史结果保留，新的 REAL 必须使用新哈希对应的 MOCK。旧协议 ID 和字段名保持兼容，不迁移、不重写历史。

## 本次可解释的比较

以同一形式内的负性 − 中性类别比例差为主要描述对比，先逐情境查看负面解释，行动意向作为另一项输出指标。无附加 Context 的比较是增加整段材料的总差异；方式间差异及差异中的差异只作次级探索，不据此宣布某种形式更有“经历感”。结果为零、反向或缺失均原样保留，不据此改题或挑选版本。

内容操纵同时改变明确拒绝的话语和图表是否保留这一结果，是一个整体事件包，不能拆解为单一“负性情绪”作用。Direct 与 Transcript 核心事实逐字相同，但引导语、编号、换行和长度不同；没有严格等 token 匹配。Interactive 还改变消息角色与位置、最近一次回答距决策的距离、调用次数及自生成内容。那些回应不是匹配过的外部事实，也不应作为协变量事后“控制掉”来宣称纯因果机制。将来如要隔离形式，可另建版本添加预先冻结的配对回应重放条件；不在首次运行前无验证扩组。

每批固定身份、模型与区域、显式参数、事件事实、情境全文、输出要求、编码模型和规则。供应商默认温度／top_p 仍是未完全控制因素；顺序 seed 不能固定模型随机性。三个重复是采样次数，静态条件会有相同输入，Interactive 重复则重新生成前缀；四个分支共享快照，是相关观测。只取三次不能可靠估计总体概率或证明没有效应。

## 与人类研究的关系

[Henricks et al. (2022)](https://link.springer.com/article/10.1007/s10802-022-00915-3) 的具体 Verbal Vignette Task 是七个模糊社交情境，让青少年分别对正面、负面、中性解释作 6 点匹配度评分；主指标为正面均分减负面均分，中性不进入该差分。研究同时测量社会恐惧，并考虑自尊和抑郁情绪；并非“随机注入经历后测记忆形成”的实验。

Demo 2 是自编中文材料、20 岁人物框架、生成式公开解释与行动意向，再作互斥分类；没有相同量表、人类样本或逐题评分。因此负面类别率不是上述量表分数，action 也不是观察到的真实行为。混合解释归 neutral 会丢失同时认可正负解释的信息，Coder confidence 是模型自报值，不是已校准的可靠度。首次 REAL 后必须保留全部原文，安排盲于条件的人工复核；若未来比较人类，需要同题同指令的桥接测量、独立人类数据及编码一致性验证，不能套用文献总体均值。

[Aher et al. (2023)](https://proceedings.mlr.press/v202/aher23a.html) 展示了复现部分人类任务及系统性失真的可能；[Cui et al., v3 (2025)](https://arxiv.org/abs/2409.00128v3) 在 156 个情境实验、三个模型上发现主效应与交互效应复现程度不同，并报告效应偏大及原零结果出现显著结果的风险。这些是方法参照，不是 Demo 2 的效度证据。当前定位为模型输出的 Context 敏感性探索；不称为直接复现 Henricks，也不以“有方向差异”等同心理拟真。另参见 [Abdurahman et al. (2024)](https://doi.org/10.1093/pnasnexus/pgae245) 对文化偏差、提示稳健性与可复现性的讨论。

## 冻结设计

七组：`none`、`neutral_direct`、`negative_direct`、`neutral_transcript`、`negative_transcript`、`neutral_interactive`、`negative_interactive`。

默认一个 Agent 模型、四情境、每组 3 次独立重复：21 份快照、84 条最终决策。Interactive 每种内容各获取 3 次，每次两轮固定事件，共 12 次获取调用。加 84 次独立编码，共 180 次正常逻辑调用；默认每调用最多尝试两次，最多 360 次，另受 400 次请求硬上限约束。MOCK 的这些请求是程序模拟，真实 API 次数为零。

`smoke_test` 固定每格一次：7 份快照、28 条最终决策、4 次获取、28 次编码，共 60 次正常逻辑调用。它与 `exploratory_mvp`、MOCK 与 REAL 分开统计。执行顺序采用记录下来的伪随机种子；先打乱条件／重复块，再打乱块内情境，始终先完成获取再分支。顺序种子不是模型采样 seed。

## 事实源与消息

`acquisition.py::EVENTS` 是唯一事实源，版本 `matched-seminar-events-v0.2.0`。包含 event_id/version、participants、event_sequence、observable_facts、exact_utterances、objective_outcome、调度专用 valence_label。每种形式由同一组事实确定性渲染，全部原始事实随快照和批次保存。只用这一对经历，不能推断所有记忆内容的普遍效应。

共同背景：上周二 16:00，三人在教室核对三页课程报告，人物展示一张图表；16:12 讨论结束并按时提交。中性版中，陈晨说“你的这段已记下，我们接着核对其他部分”，图表被保留；负性版对应话语为“你的这段不想听，我们直接跳过你的部分”，图表未被保留。第二名同学的话语与结果同样记录。无焦虑、低自尊、后续行动策略等描述。

| 形式 | 生成前消息结构 |
|---|---|
| none | 固定 system → 当前情境 user |
| direct | 同一 system → user：按事实顺序连接的简短过去经历 → 当前情境 user |
| transcript | 同一 system → user：同样事实的编号静态记录 → 当前情境 user |
| interactive | 同一 system → 固定事件第一段 user → Agent 简短回应 assistant → 固定事件第二段 user → Agent 简短回应 assistant → 冻结；每个分支独立追加当前情境 user |

Direct/Transcript 各核心事实逐字相同、顺序相同。Interactive 的外部事实和其他人物话语由同一事实源分两轮呈现；Agent 回应不改变程序事件，但其自生成文本留在快照中，属于明确的混杂因素，不将它称为纯粹“经历感”。完整消息示例可在页面预览；已运行批次可检查真实冻结快照。预览不会伪造 Interactive 回应。

公开输出版本 `acquisition-situated-public-v0.2.0`：单个 JSON 对象，`interpretation` 为简短公开解释，`speech` 为实际话语、可为空，`action` 为一个具体下一步行动、可以明确暂不行动。它不要求隐藏推理链，不要求解释记忆如何影响行动。所有组使用同一身份、第一人称情境框架和输出要求。

## 四个独立情境

情境文本版本 `acquisition-scenarios-v0.2.0`，完整文字以代码中的固定值和批次配置为准，运行中不能编辑。全部 `held_out=false`；没有声称保留题已验证。

| ID | 类别 | 场景与机会 |
|---|---|---|
| S1_near | near | 新课程小组跳到下一页，尚未评价图表；可询问、继续讨论或离开 |
| S2_near | near | 社团物料建议暂未处理；可询问、等待或退出筹备 |
| S3_far | far | 食堂同学拿起空椅上的包，尚未开口；可询问、稍等或换桌 |
| S4_control | control | 独自在打印区等待处理中的任务；可查看、等待或取消 |

S3 的远迁移与 S4 的无关性是研究假设，不代表难度等价或已验证心理结构。提供明确行动机会也可能影响行为分布，但对所有条件保持一致。不因效应大小改题。

每份快照分四支；S1 的解释、话语和行动绝不进入 S2–S4。每次请求重发完整消息，不使用服务器会话 ID、previous_response_id、自动总结、反思或记忆检索。快照与调用审计由 SQLite 触发器禁止更新／删除，取用时检查哈希并解码出独立副本。

## 独立编码与分析

版本 `acquisition-public-fields-v0.2.0` 映射现有 `design.CODER_VERSION` 的规则及冻结 coding_rules。类别不作事后调整：解释 positive / neutral / negative / unclear；行动 approach / wait / avoid / other。解释只从公开 interpretation 字段编码，行动只从 action 字段编码；speech 不替代行动。仍保留旧规则中混合解释归 neutral 的限制。Agent 与 Coder 是分开的请求；Coder 只收到当前情境、三项公开字段和规则。不主动给记忆、组别或预期；回答自身提到过去时保留原文，并记录潜在盲法限制。

按来源、阶段、精确配置、返回模型标识／fingerprint、情境分层，逐格显示计划／已记录／有效数、全部标签和计数、经验比例、失败及原文。unclear/other 属于有效类别，不删掉；未编码／未发出单列，不当作负面缺失。页面百分比只取整，并优先显示分子／分母。

分别报告负性与中性相对无记忆的差值；同一内容的获取方式差值；每种获取方式的 `负性比例 − 中性比例`；方式之间上述差值的差，即探索性的差异中的差异。对四个解释类别和四个行动类别均计算，主要浏览负面解释与回避行动。缺失格未配齐时不计算差值。无跨情境平均分、p 值、自动成功结论或人类拟真评分；四分支是相关观测，3 次重复不能估计可靠总体概率。

## 存储、Provider 与费用

复用原 `trials` 保存最终决策，原 `settings` 保存批次状态及人工 Gate 3 复核。首次运行本协议时，先用 SQLite backup API 备份，再增量建立 `acquisition_snapshots` 与 `acquisition_call_events`，不改写旧表中的记录。只读预览不触发迁移。JSON/CSV 审计导出包含决策、快照、获取和重试事件、运行状态及分析，连“获取失败而没有最终决策”的批次也可导出。

每次调用保存发送前完整 body（不含 Authorization）、消息角色／顺序／位置、公开原文、usage、实际返回的模型标识／fingerprint、重试与错误。HTTP 错误正文可能含凭据，故只保存状态码和安全错误分类。没有本地匹配 tokenizer 时，不伪造记忆片段 token 数：保存字符／UTF-8 字节数，token_count=null；整次输入、输出与缓存 token 原样来自返回 usage。`seed` / `top_p` 本适配器尚未核实，明确未发送、值为 null。可变模型别名不等于确定权重版本，缺少精确版本时记录未知。

MVP 暂只开放 DeepSeek / MiniMax 的完整无状态消息传输；这只是客户端实现支持，真实型号仍须 Gate 3 验证。其他 Provider 在原协议中保留，本协议拒绝而不把 Interactive 降级。接口依据：[DeepSeek messages](https://api-docs.deepseek.com/api/create-chat-completion/)、[MiniMax Chat Completions](https://platform.minimax.io/docs/api-reference/text-chat-openai)。不额外填充缓存前缀，不保证触发缓存，不宣称节省比例。

REAL 前需填写已核实的输入／输出单价、币种和预算。每次尝试前检查总请求上限并保守预留下一次费用；按返回 usage 与用户单价核算，缓存按未折扣价格处理。网络失败无法得知是否计费时保留预留，usage 缺失则停止后续调用。预留输入按 UTF-8 字节数加消息开销估算，不是精确 tokenizer 上界或供应商账单保证；应配合供应商账户额度。超预算、认证失败、限流重试耗尽、消息隔离失败、模型版本变化或第一条解析失败均停止，不通过改 Prompt 隐藏错误。中止不会撤销已经在途的请求。

修订后的 REAL 输入和输出计价必须为正数，防止用零单价使预算保护失效；优惠和缓存折扣可在账单核对时单列，不据此取消预留。Gate 2／3 会逐调用核对请求 body、参数、重试配对、公开原文和 usage 是否与冻结分支相符；Gate 3 同时绑定决策、快照和完整调用审计哈希。后续变更审计或增加未经复核的快照不能沿用放行结果。客户端记录只能证明发送与保存的公开历史，不能证明供应商内部绝无重排或隐含状态。

## Windows 操作与 Gate

双击 `启动EchoMind.bat`（调用 `start_mvp_windows.bat`），访问 `http://127.0.0.1:8769/#acquisition`。工作台使用 EchoMind 自己的 `data/pilot.sqlite3`；新旧协议各自统计。自动化验证全部使用临时数据库；最终保存的演示批次明确标为 MOCK，不是付费模型实验。

```powershell
Set-Location C:\Users\Kayla\Desktop\EchoMind
# 只预览：不调用模型
& 'C:\Program Files\Python311\python.exe' mvp_cli.py
# 在 EchoMind 数据库新增 84 条 MOCK；--output 须选择尚不存在的新文件
& 'C:\Program Files\Python311\python.exe' mvp_cli.py --run --output data\my-mvp-mock.json
# 浏览同一验证库
.\start_mvp_windows.bat
# 所有自动测试均使用临时库或注入的假 transport
$env:ECHOMIND_OFFLINE='1'
& 'C:\Program Files\Python311\python.exe' -m unittest discover -s tests -v
& 'D:\Program Files\nodejs\node.exe' tests\browser_acquisition_smoke.mjs
```

Gate 1：核查原系统与备份。Gate 2：同配置完成 84 条 MOCK，校验快照、事实覆盖、隔离、盲编码、错误及数据库重算。MOCK 不能替代真实 Provider 验证。

**REAL smoke 只由用户手动启动**：关闭自己打开的离线服务窗口，按已有方式在本机配置 API Key；不要将密钥填入网页或请求 JSON。使用同一数据库启动非离线服务（下面命令本次未执行）：

```powershell
Remove-Item Env:ECHOMIND_OFFLINE -ErrorAction SilentlyContinue
$env:ECHOMIND_PILOT_DB=(Join-Path (Get-Location) 'data\pilot.sqlite3')
& 'C:\Program Files\Python311\python.exe' server.py --port 8769 --open-browser --open-path '/#acquisition'
```

在记忆获取页选择 REAL → smoke_test，选择已完成的同配置 84 条 MOCK 批次；填写模型与单价、预算；预览 28 条决策／60 次逻辑调用；明确勾选并运行。完成后查看全部实际消息、快照、输出、usage，在 Gate 3 区由用户填写复核人、记录并确认五项检查。保存复核不会启动下一批。

首次付费运行建议：先只批准 smoke，最多尝试 1 次、最大请求数 60、并发固定 1；该批没有自动重试，失败就保留现场再检查。正式 MVP 另行批准，三次重复、请求数 180、最多尝试 1 次。各批预算分别核准，程序没有跨批共享钱包，不能把“每批预算”当作总预算。命令 `python -u .\mvp_cli.py --serve --db .\data\pilot.sqlite3 --port 8769` 强制离线，仅用于查看和 MOCK；不要用它尝试开启 REAL。当前审查不会启动付费实验或填报人工 Gate 3。

Gate 4：只有匹配配置的 REAL smoke 完整且人工复核通过，才允许选择该 smoke 批次运行三重复 REAL MVP。变更事件、情境、身份、模型参数、Prompt 或编码规则会改变哈希，需要重新验证。当前本次交付只验证 Gate 1–2；未进行任何真实付费 smoke 或 MVP，不能宣称 Gate 3 已通过。
