# SOS 历史数据恢复报告

审计日期：2026-10-21。项目：`experiments/context_memory_pilot`。

## 结论

原实验 A、实验 B、MiMo 60 次认证失败记录均未丢失。修复的是历史访问、展示与持久化机制，没有重建数据、重编码旧回答或覆盖数据库。

初查主库有 **362 条记录、14 个批次**，其中真实调用完成 144 条、真实调用失败 137 条、MOCK 完成 81 条。修复期间另一个服务运行进程新增批次 `958e4338-ab90-4f0b-85dc-8c523e246723`：DeepSeek / memory-ratio-v1，60 条真实完成，UTC 08:08:36–08:09:20。它单独保留，不纳入本报告的原实验 A/B。当前审计快照为 **422 条、15 个批次**。本轮自动验证没有发起真实模型调用。

“恢复”具体是：让初始 362 条记录重新在统一历史入口可见；从外部文件补写 **0 条**，删除 **0 条**，静默改写旧结果 **0 条**。新的记录仍可通过相同入口访问。

## 数据库与导出核查

| 项目 | 发现 |
|---|---|
| 主库 | `data/pilot.sqlite3`，初查 8,966,144 字节，SQLite integrity_check = ok |
| 修复前备份 | `data/backups/before-research-repair-20261021T073548Z.sqlite3`，SQLite 在线备份接口生成；362 条记录，完整性检查通过 |
| 初始哈希清单 | `data/recovery-before.json`，每个原 payload 的 SHA256；备份路径及总哈希一并记录 |
| A 原导出 | `../../demo_results/2026-10-21-820cb1f4.json`，60/60 条与数据库逐字段相同 |
| MiniMax 原导出 | `../../demo_results/2026-10-21-minimax-91eb2e68.json`，60/60 条与数据库逐字段相同 |
| B 原导出 | 未找到单独旧 JSON，但完整 24 条仍在 SQLite；已另存原记录导出 |
| 新审计证据 | `data/research-audit/inventory-and-metrics.json`、`A-original.json`、`B-original.json`、`MiMo_failed-original.json`、`all-original-records.json` |

搜索覆盖 SOS 项目树内 `.sqlite3/.sqlite/.db/.bak/.zip` 及相关 JSON；排除临时浏览器缓存。另核对常见误建位置（用户目录、Desktop/SOS、experiments 下的 data/pilot.sqlite3）。除本轮新建备份外只发现上述一个主库。没有扫描整个磁盘，也不能据此排除未提供的外置盘或其他目录。

数据库原有四张表：`settings`（设计配置）、`trials`（索引字段及完整 JSON payload）、`human_ground_truth`、`state_human_datasets`。本轮 **没有 schema 迁移**。新任务状态与不可覆盖的 Prompt 版本存入现有 settings 的独立命名空间，不修改旧 design 或旧 trial。

## 为什么页面看不到

1. 初查 `http://127.0.0.1:8768/` 及所有实验 API 均连接拒绝，当时服务未运行。这只能解释当时的不可访问，不能证明此前消失事件的唯一原因。
2. 原统一页面实际上只有两套独立实验视图。各自只读取 `memory-ratio-v1` 或 `memory-ablation-v1`；旧 `/api/trials` 还明确排除了这些协议及 anxiety-state-v1。没有覆盖全库的历史列表。
3. 两套页面默认选择最新批次，而当时最新机制批次和最新消融批次都是 MiMo 401 失败。成功的 A/B 排在更早位置，容易被最新失败结果遮住；不是有效记录被删除。
4. 旧任务队列只保存在进程内。重启后 `/api/jobs/{id}` 找不到任务，尽管 trial 仍在。现已区分“历史批次”“已中断任务”“当前任务”。
5. 原默认数据库路径本身已以 server.py 目录构造绝对路径，**不是默认路径依赖 cwd**。但 `SOS_PILOT_DB` 若给相对路径，旧 Store 会依赖工作目录，确有误建新库风险。本次未找到这种第二主库。现所有相对覆盖路径都锚定项目目录，健康接口和页面显示解析后的绝对路径。
6. 启动器以前只探测旧机制 bootstrap，可能把旧代码进程当作新版服务。现在健康接口报告代码指纹，启动器发现代码已更新会提示重启。新旧 JS 已采用 IIFE，不应无证据地归因为全局变量冲突。

因此，可证实的是“数据在、历史入口碎片化、最新失败默认选中、任务进程状态易失、初查服务离线”；没有旧浏览器日志，不能给此前前端消失事件断言唯一根因。

## 原始批次清单

下表状态均按存储原值，成功不等于研究结论成立。

| 批次前缀 | 协议 | 来源/模型 | 成功 | 失败 |
|---|---|---|---:|---:|
| 854e2532 | 未标注旧版 | MOCK / gpt-4.1-mini | 1 | 0 |
| 89603c3f | 未标注旧版 | MOCK / gpt-6-luna | 5 | 0 |
| 78fd5276 | 未标注旧版 | LIVE / DeepSeek | 3 | 2 |
| 7cc20b61 | anxiety-state-v1 | MOCK / DeepSeek | 3 | 0 |
| **820cb1f4** | **memory-ratio-v1** | **LIVE / DeepSeek，实验 A** | **60** | **0** |
| 91eb2e68 | memory-ratio-v1 | LIVE / MiniMax | 57 | 3 |
| 4f4e9970 | memory-ablation-v1 | MOCK / DeepSeek | 24 | 0 |
| **46c4575c** | **memory-ablation-v1** | **LIVE / DeepSeek，实验 B** | **24** | **0** |
| 8b8344c0 | memory-ablation-v1 | MOCK / DeepSeek | 24 | 0 |
| d282a15d | memory-ablation-v1 | MOCK / DeepSeek | 24 | 0 |
| 9f853293 | memory-ablation-v1 | LIVE / DeepSeek，401 | 0 | 24 |
| cd0b60bc | memory-ablation-v1 | LIVE / MiMo，401 | 0 | 24 |
| da57b3ef | memory-ablation-v1 | LIVE / MiMo，401 | 0 | 24 |
| **cd574596** | **memory-ratio-v1** | **LIVE / MiMo，401** | **0** | **60** |

完整 UUID、时间、模型、协议、状态及各单元格统计见 inventory-and-metrics.json。

## 已实施的保护

- 历史默认列出所有协议、模型、来源和状态；日期按 Asia/Shanghai 的批次首条记录筛选。状态筛选选批次，不改变打开后的分析分母。
- 逐条显示保存的 role_messages / evaluator_messages / narrative / evaluator_raw / machine_coding / 模型参数 / snapshot / 错误 / ID。展示实际记录，不用当前 Prompt 重新拼接冒充旧 Prompt。
- 缺少协议显示为 `legacy-unspecified`，只是视图标签，不补写 payload。失败无原始回答时明确显示缺失，不编造。
- 历史描述视图按协议、来源、模型配置、编码版本、情境、记忆条件、格式、材料版及 Prompt hash 分格；原协议报告单独保留。不同协议不合并计算显著性。
- JSON 完整导出所有字段；CSV 追加完整记录 JSON、角色/编码 Prompt JSON 和模型参数。旧导出接口仍可用。
- 任务元数据持久化；重启后的未结束任务标为 interrupted，保留原 trial 状态，不自动续跑付费调用。旧任务只恢复存储事实，不猜原队列进度。
- HTTP 401/403 立即停止调度，429 在单调用最多三次尝试后停止批次；连续三条失败停止后续调度。已有最多三个并发试次可完成，未发出的试次不伪装成失败输出。

## JSON 导入与可恢复性

历史页选择 JSON → 预览 → 查看新增/重复/冲突数量 → 确认导入。支持现有 `{records:[...]}` 导出及记录数组；只有汇总计数的文件拒绝。必须保留原 id、带时区 timestamp、source、status；未知字段保留。

相同 ID 和相同内容跳过；同 ID 内容不一致则整份拒绝。导入是单事务 INSERT，无覆盖/UPSERT trial。实际写入前创建带唯一文件名的 SQLite 备份并校验完整性。重复提交不增加记录，不重复备份。发现凭据字段、NaN、重复 JSON 键、错误导出哈希时拒绝。

浏览器发送**原始文件文字**到服务器解析，避免 JavaScript 把 64 位 order_seed 舍入或把 `1.0` 改成 `1` 后破坏校验。原始 payload 的字符串哈希用于核对既有数据未变化；导入去重按解析后的完整字段内容比较。

如需从备份回退：先停止服务，将现库另存保留，再以 `SOS_PILOT_DB` 指向备份的**工作副本**检查。确认记录后再切换，不直接覆盖唯一主库。本轮没有执行回退。

## 无法“恢复”的内容与验收

A/B 的本地原记录完整；MiMo 失败批次没有成功回答可恢复，只有原始错误与当时配置。早期批次未保存的进程队列状态、未返回的模型响应、没有记录的旧字段无法倒推。部分模型原始 HTTP 响应/隐藏推理从未入库，此处“原始回答”指当时保存的用户可见 narrative 及 evaluator_raw，不声称恢复不存在的供应商报文。

运行 `python tests/recovery_audit.py` 可复核原 362 个 payload 与备份前清单一致，并生成分离的审计导出；它只读主库。最终验收结果与浏览器截图见 TEST_REPORT.md。
