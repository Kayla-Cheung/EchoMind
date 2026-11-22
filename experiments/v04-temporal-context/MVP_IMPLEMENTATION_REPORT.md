# EchoMind Memory Acquisition MVP v0.2 — 实现与验收

日期：2026-10-23。当前唯一工作目录：`C:\Users\Kayla\Desktop\EchoMind`。本实验已从 SOS 独立出来；运行时不访问 SOS 文件夹，不使用 SOS 的数据库或离线环境变量。历史试次保留原始协议和来源信息。

## 1. 路径与架构

入口为 `启动EchoMind.bat` → `start_mvp_windows.bat` → `mvp_cli.py --serve`，默认打开 `http://127.0.0.1:8769/#acquisition`。这仍是原工作台的增量扩展，旧协议、旧页面和历史记录保留。

`runner.py` 按协议分派；`acquisition.py` 负责冻结材料、获取、分支、编码和分析；`model_client.py` 使用独立无状态请求；`storage.py` 保存 SQLite；`server.py` 暴露已有及新增 API；`web/unified.html` 增加一个“记忆获取 MVP”标签，配合 `acquisition.js/css`。当前系统不包含长期世界、多 Agent、人格引擎、RAG 或训练。

## 2. 修改范围

主要新增：`acquisition.py`、`mvp_cli.py`、`start_mvp_windows.bat`、`MVP_PROTOCOL.md`、本报告、`web/acquisition.js`、`web/acquisition.css`、`tests/test_acquisition.py`、`tests/test_acquisition_http.py`、`tests/browser_acquisition_smoke.mjs`。

主要扩展：`runner.py`、`storage.py`、`model_client.py`、`server.py`、`history.py`、`web/unified.html/js`、`web/history.js`。EchoMind 启动脚本、环境变量、浏览器任务标识及相关旧测试一并调整为独立命名；旧试次和 Prompt 版本不改写。`README.md`、使用教程和测试报告补充当前入口。逐文件变更及哈希见 `data/acquisition-v02-change-manifest.json`。

迁移前源码及数据库备份：`data/backups/before-acquisition-v02-20261023T125519Z/`。现有 EchoMind Git 工作区此前已有未提交更改，本轮保留它们，没有提交或推送。

**Git 限制**：当前工具环境将 `EchoMind/.git` 声明为只读，`git switch -c feat/memory-acquisition-v02` 创建引用失败。功能分支尚未创建，代码保留为当前工作区的未提交更改。可在具有 Git 写权限的普通 PowerShell 中执行同一命令建立分支；没有绕过限制修改 `.git`。

## 3. 数据库与旧数据保护

唯一默认运行库为 `data/pilot.sqlite3`。首次运行新协议前自动备份：

`data/backups/before-memory-acquisition-v02-schema-20261023T130612823088Z-bdbd128f.sqlite3`

| 表 | 当前行数 | 本轮用途 |
|---|---:|---|
| trials | 530 | 原 446 条逐条 payload 完全一致；新增 84 条、全部 MOCK |
| settings | 5 | 原 3 项不变；增加协议迁移记录与演示批次状态 |
| human_ground_truth | 0 | 未改动 |
| state_human_datasets | 0 | 未改动 |
| acquisition_snapshots | 21 | 新增不可更新／删除的冻结快照 |
| acquisition_call_events | 360 | 新增不可更新／删除的请求、回应、重试与错误事件 |

迁移为备份后的增量建表，不重建数据库。再次执行不会重复迁移。SQLite 完整性检查 `ok`。验证凭据：`data/acquisition-v02-verification.json`。旧数据、旧配置没有重新编码或覆盖。网页和启动器均验证当前 EchoMind 路径；旧 SOS 环境变量不会改变数据库位置。

## 4. 七组实现与消息示例

| 条件 | 内容 | 获取 | 默认快照数／最终记录数 |
|---|---|---|---:|
| none | 无事件 | 只有同一基础角色 | 3／12 |
| neutral_direct | 中性 | 一条过去经历描述 | 3／12 |
| negative_direct | 负性 | 一条过去经历描述 | 3／12 |
| neutral_transcript | 中性 | 一条编号静态事件记录 | 3／12 |
| negative_transcript | 负性 | 一条编号静态事件记录 | 3／12 |
| neutral_interactive | 中性 | 两轮固定事件，各接一条公开回应 | 3／12 |
| negative_interactive | 负性 | 两轮固定事件，各接一条公开回应 | 3／12 |

Direct 与 Transcript 由同一结构化事件事实逐字渲染，呈现顺序相同。Interactive 使用同一事实源分两轮给出环境和其他人物的话语；Agent 不改变外部事件结果。每次获取后的完整公开历史冻结，再复制给四个独立情境。任何情境的最终回应都不写回记忆。

实际发送的消息可在 `message-preview.json` 查看；演示产生的完整快照在 `memory-snapshots.json`。例如中性 Direct 的 user 内容以“你过去经历过这件事：”开头，随后依事实源连接“上周二下午四点，你、陈晨和许宁在教室参加课程小组讨论。……”；Transcript 以“你过去参与的事件记录：”和逐条编号呈现同样事实。Interactive 的消息角色是 `system → user → assistant → user → assistant`，本次 MOCK 的两条 assistant 均为程序样例“我听到了。”，不是来自真实模型。

每个分支独立追加当前情境及相同 JSON 输出要求：`interpretation`、`speech`、`action`。Coder 为另一条请求，只接收当前情境、三个公开字段和冻结规则；解析结果不替代原文，原始 final-channel 文本片段另保存在 `raw_public_parts`，包括原始空白。隐藏 reasoning 字段不作为行为材料。

## 5. 已保存的 MOCK 结果

批次 ID：`db419e06-c139-4aa7-8a38-f9565a32a06b`；阶段 `exploratory_mvp`；来源 `MOCK_NOT_LLM`。

- 84／84 条决策完整，失败 0；21 份快照，四个情境各 21 条记录。
- 12 次交互获取 + 84 次决策 + 84 次独立编码 = 180 次模拟请求，形成 360 条请求／回应审计事件。
- 真实 API 请求为 0，没有读取本地 `.env` 或发起付费实验。
- MOCK 在每个条件／情境使用相同的三个预设文本与分类：解释 unclear、neutral、negative 各一次，行动 wait、approach、avoid 各一次。各组负面解释和回避均为 1／3，方式间差异为 0。

这些相等结果是程序设计的流程样例，只能检验输入隔离、统计与持久化；不能说明真实 LLM 存在或不存在记忆效应。

结果目录：`data/memory_acquisition_v02/20261023T130612Z/`

| 文件 | 内容 |
|---|---|
| full-audit.json | 完整决策、实际消息、原文、编码、快照、调用与分析 |
| full-audit.csv | 带 row_type 的全量审计，包含获取失败等无最终决策情形的表示格式 |
| analysis.json | 按来源／阶段／配置／情境分层的分类与差值 |
| memory-snapshots.json | 21 份冻结快照和交互中间记录 |
| message-preview.json | 七组的固定事实和完整消息结构 |

## 6. 自动化验收

全套 **81 项通过，47.258 秒**。涵盖七组、事实覆盖、3 次独立交互获取、快照不可变、四分支隔离、盲编码、预览哈希、缺失密钥、预算和中止、401／429／重试、解析失败、原始文本保存、数据库重算、服务重启、协议隔离、CSV／JSON 导出及既有协议回归。

三组 Edge 浏览器验收通过：

- 新获取协议：84 条 MOCK、运行中刷新恢复、七组预览、21 份快照、完整审计导出、桌面／390px 手机，无 JS 异常。
- 原来源对照 v2：独立临时库中 8 + 192 条 MOCK，原流程保留。
- 历史页：原库的只读快照中检查 446 条／16 批，原 A 60 条、B 24 条、失败筛选、原始 Prompt、重复导入和版本保存。

全部自动化写入在临时库；另外明确运行并保存了上节一批演示 MOCK。测试输出为 `data/acquisition-v02-unittest.txt`，浏览器证据为 `data/acquisition-v02-browser-result.json` 及 setup/results/mobile PNG。当前服务代码指纹 `72a7512284f93b90`。

## 7. 启动、运行和 REAL smoke

```powershell
Set-Location C:\Users\Kayla\Desktop\EchoMind
.\启动EchoMind.bat
# 只预览默认 84 条方案
& 'C:\Program Files\Python311\python.exe' mvp_cli.py
# 明确新增一批 MOCK，并导出到尚不存在的新文件
& 'C:\Program Files\Python311\python.exe' mvp_cli.py --run --output data\my-next-mock.json
```

当前入口 `http://127.0.0.1:8769/#acquisition` 已在离线模式运行。刷新或重启后从 SQLite 取回历史，不自动重试付费任务。

**Gate 1–2 已验证，Gate 3 未运行，Gate 4 REAL 未解锁。** 用户需要按 [MVP_PROTOCOL.md](MVP_PROTOCOL.md) 的命令手动切换非离线服务，配置自己的密钥，在页面选择 REAL / smoke_test、同配置的 84 条 MOCK 前置批次，核实单价与预算，预览后明确确认。28 条 REAL 决策完整后，由用户核对实际消息、隔离、Provider 历史语义、解析和 usage，并填写人工 Gate 3 复核。保存复核不会自动运行 84 条 REAL。当前数据库没有任何 Gate 3 通过记录。

## 8. 尚未消除的限制

只有一对记忆事件；四情境的 near/far/control 分类与难度等价尚未验证；Interactive 同时增加自生成文本、消息位置、长度和调用次数。三次重复只能产生粗糙经验比例，同快照的四个结果相关。现有互斥编码会把混合解释归 neutral，尚需双人盲评。真实 Provider 是否完整保留多轮语义需要 Gate 3，不能由 MOCK 推断；可变模型别名不保证权重版本固定。

不自动做显著性检验，不用更多负面回答定义改进，不声称焦虑、创伤、主观情绪、“经历感”或 Human Psychological Fidelity。下一步应先完成并人工审查 28 条 REAL smoke，之后才考虑本协议的探索性比较。
