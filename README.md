## 界面更新：单一主页（2026-10-21）

访问 `http://127.0.0.1:8768/`，顶部两个标签切换“经历强度对比”和“记忆归属 × 输出格式”两种实验。旧地址 `/ablation` 仍可打开同一个工作台并默认选中消融实验；可用 `/#ablation` 直达消融模式。两种协议、历史批次、实际 API 调用、模型提示和导出入口保持隔离，不能混合计算显著性。本次只合并网页导航与展示入口，不会迁移或改写 SQLite 数据。

# SOS Context-Driven Behavioral Simulation Lab

## 新增：记忆归属 × 输出格式消融实验（2026-10-21）

访问 `http://127.0.0.1:8768/ablation`：独立于原机制 Demo 的 4 个记忆来源条件 × 2 种格式，使用新版严格编码 `blind-ablation-v2.0`。默认每格 3 次 MOCK、共 24 条不收费模拟回答；可选择真实 API，运行前会单独确认预计调用数。保存全量原文与提示、完整/失败分母并可导出 JSON/CSV。**结果仅描述，不自动判定焦虑模拟成功**。详见 [ABLATION_DEMO.md](ABLATION_DEMO.md)。旧版 `/`、`/study`、`/workbench` 保持原协议、历史统计互不混合。

本次交付的源码 ZIP 和补丁 ZIP **不包含** `data/pilot.sqlite3`、`.env`、API Key、浏览器缓存/Cookies/Login Data 及用户历史数据。**升级时必须在原文件夹覆盖源码文件，而非删掉原目录重建**，并先备份自己的 `data/pilot.sqlite3` 和 `.env`。如端口 8768 已有服务运行，须停止旧进程后重启才会加载新的后端代码。

## 当前首页：同题重复采样机制 Demo

从 SOS 根目录双击 `启动Demo.bat`，打开 **http://127.0.0.1:8768/**。默认同一问题、三个经历条件、每组 20 次，输出“内心想法 / 说话（可选）/ 行为（可选）”。完整分布、分子分母、区间、逐次原文和预设的探索性判断直接展示。MOCK 不构成模型证据；真实批次整批完成后才判断。简明教程见根目录 [Demo使用教程.md](../../Demo使用教程.md)，方法见 [MECHANISM_DEMO.md](MECHANISM_DEMO.md)。

新协议 `memory-ratio-v1` 与历史状态协议、旧记忆协议分别统计。原三档研究页移到 `/study`，原记忆页仍在 `/workbench`。旧 SQLite 记录保留。下面是这些旧页面的说明；旧的 8766 服务可继续存在，新启动入口统一为 8768。

## 原三档状态诱导页

打开 `http://127.0.0.1:8768/study`，选择一个角色模型和一个情境，点击“运行三档对比”。默认 MOCK，三次模拟试次，不调用 API。无 / 轻度 / 中度为外部诱导目标，不是已验证的心理状态或诊断。切换真实 API 后会先显示调用量并要求明确点击确认。

高级设置可加入无记忆、负面非社交经历对照，选择 A/B/C 材料版、开发 / 预留评估情境、重复次数和固定编码器。所有角色调用使用相同身份和独立上下文；三档程度标签不进入角色提示。材料可编辑保存，结果保留快照并按协议、人物提示、模型、编码器、批次区分。完整实验设计、价值判断与否证条件见 [STUDY_DESIGN.md](STUDY_DESIGN.md)。

页面的人类参照区域默认为空，可导入带来源、工具、分组依据和编码版本的 CSV；不内置合成人类数据。只有真实 API 结果、确认可比的相同情境和编码版本会计算描述性分布差值。没有真实人类数据时，外部有效性始终标为未检验。

原记忆实验页面位于 `/workbench`，其记录单独展示；历史 SQLite 试次保留。新增协议存于 `settings` 的独立键，新增 `state_human_datasets` 表，不清空旧人类数据表。编码器 v1.1 明确了非社交场景中“主动处理 / 放弃处理”的含义，旧 v1.0 编码不会被重写。

验证命令：`python -m unittest discover -s tests -v`。可选 Windows 浏览器验收：`node tests/browser_state_smoke.mjs`（Node 22+、已安装 Edge）；它使用临时 SQLite，仅运行 MOCK，不修改正式实验库。

## 原记忆工作台

首页现在按三步操作：① 勾选角色模型（五家 Provider 卡片，模型 ID 在卡片内展开修改）；② 选择记忆条件和固定情境；③ 选择 MOCK 或真实 API，运行当前条件或五条件对比。右侧显示第一人称回答及独立编码。连接测试、生成参数、Prompt Inspector、调用上限等收在卡片或“高级设置”中；完整记录与研究材料仍在“查看结果”和“研究设置”。

此机上原三档服务仍占用 8766 端口，因此当前 Windows 启动脚本与默认端口改为 **8768**。访问 `http://127.0.0.1:8768/workbench` 查看原记忆工作台。旧版界面备份为 `web/index_previous.html`，SQLite 数据未迁移或清空。

## 本机 API Key 配置

如果是原本已配置的项目，目录里可能有本机专用 `.env`，并由 `.gitignore` 排除。用记事本打开 `.env`，把需要使用的密钥填在相应等号后，例如 `DEEPSEEK_API_KEY=你的密钥`；其他四项分别是 `MINIMAX_API_KEY`、`MIMO_API_KEY`、`GEMINI_API_KEY`、`OPENAI_API_KEY`。保存后重新启动 `start_windows.bat`。服务启动时自动读取 `.env`；同名系统环境变量优先。空白项保持未配置。请不要把真实密钥写进 `.env.example`，也不要提交 `.env`。

连接测试仅在界面中手动点击后发起，可能产生费用。填写密钥本身不会触发 API 调用。

本地 **Mechanism Pilot**：保持人物与情境一致，操纵研究者合成的自传式记忆，描述模型解释和行动如何变化。本工作台不声称拟合真实人类焦虑行为。MOCK 只用于工作流验收。

## Windows 启动

需要 Python 3.10+，无需安装第三方包。双击 `start_windows.bat`，保持首次启动的命令窗口打开；访问 `http://127.0.0.1:8768/`。服务只监听 `127.0.0.1`。数据保存在 `data/pilot.sqlite3`，升级不会重建或清空数据库。若新版已经运行，启动器会直接打开页面。

## 五家 Provider

| Provider | 默认模型 ID（可编辑） | 官方 API Base URL | 本机环境变量 |
| --- | --- | --- | --- |
| DeepSeek | `deepseek-flash` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |
| MiniMax 国际站 | `MiniMax-M3.1-Flash` | `https://api.minimax.io/v1` | `MINIMAX_API_KEY` |
| MiniMax 中国大陆站 | 同上 | `https://api.minimaxi.com/v1` | `MINIMAX_API_KEY` |
| Xiaomi MiMo | `mimo-v2.6-flash` | `https://api.xiaomimimo.com/v1` | `MIMO_API_KEY` |
| Google Gemini | `gemini-3.8-flash` | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` |
| OpenAI GPT | `gpt-6-luna` | `https://api.openai.com/v1` | `OPENAI_API_KEY` |

启动前在 **同一个 CMD 窗口**设置你要使用的密钥，例如：

```cmd
set DEEPSEEK_API_KEY=你的密钥
set MINIMAX_API_KEY=你的密钥
set MIMO_API_KEY=你的密钥
set GEMINI_API_KEY=你的密钥
set OPENAI_API_KEY=你的密钥
start_windows.bat
```

只设置需要的 Provider 即可。密钥不写入前端、SQLite、日志或 Git。MiniMax 请按账号区域在界面选择**国际站**或**中国大陆站**；地址仅限官方域名。默认模型 ID 不保证你的账号有权限；修改模型 ID 后，用该行“连接测试”按钮验证。连接测试会产生最小模型调用和可能的费用，只有明确点击并确认后才执行。初始连接状态显示“—”（已配置但未测试）或“未配置”；测试后显示“可用”或“失败”。

## 五模型 × 五条件 × 单情境

1. Experiment 页固定“林知”和默认“已读未回复”情境。在 Multi-Model Comparison 勾选五家，核对各模型 ID。
2. 选择一个**固定编码器**，默认 OpenAI `gpt-6-luna`。所有角色模型的原始回答都交由这个同一个编码器。编码器只看到情境、回答和编码规则，不知道角色 Provider、记忆条件或研究预期。
3. 重复次数设为 1，点“对比全部条件”。预计 **25 次角色调用 + 25 次编码调用**。先用 MOCK 检查流程；真实 API 会在运行前再次显示次数与费用风险并要求确认。
4. 在 Results 页选择数据来源，查看 Model Comparison 表、各模型自己的 Baseline 差异、原文及失败和未定类比例。MOCK 与真实 API 始终分开统计。

“单次运行”只执行当前条件 × 所勾选角色模型 × 当前情境。 “对比全部条件”执行当前情境下五条件。 “批量实验”执行所选模型 × 全情境库 × 五条件 × 重复次数。顺序随机化，单条试次使用独立的两消息角色上下文；编码器另开独立调用。每批可设置最大角色调用量 1–1000 和并发 1–3；取消会阻止尚未发出的调用，已在途请求需完成或超时。HTTP 429/5xx 与暂时性网络错误最多重试 3 次，错误也写入试次记录。

## 参数、结果与费用

适配器会校验可明确支持的推理等级、thinking 和 temperature 组合。空字段表示**供应商默认**，其实际值可能在不同模型间不同；不能假称统一温度。未知自定义模型仅允许供应商默认生成参数，能力须通过官方文档和手动连接测试重新确认。MiniMax 和其他兼容接口中的 `reasoning_content` 不进入角色回答或编码器；仅保存面向用户的非空最终文本。完整发送参数、返回模型名、Token 用量、耗时和尝试次数记录在 JSON 试次中；CSV 展平常用字段。费用栏显示 Token 和“账单核算”，因为缓存、地区、套餐与价格变化会影响实际账单。

参考官方文档：[DeepSeek Chat API](https://api-docs.deepseek.com/api/create-chat-completion/)、[MiniMax Chat API](https://platform.minimax.io/docs/api-reference/text-chat-openai)、[MiMo Chat API](https://mimo.mi.com/docs/en-US/api/chat)、[Gemini OpenAI 兼容 API](https://ai.google.dev/gemini-api/docs/openai)、[OpenAI GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)。价格请查各家的官方价格页：[DeepSeek](https://api-docs.deepseek.com/quick_start/pricing)、[MiniMax](https://platform.minimax.io/docs/pricing/overview)、[MiMo](https://mimo.mi.com/docs/en-US/pricing)、[Gemini](https://ai.google.dev/gemini-api/docs/pricing)、[OpenAI](https://developers.openai.com/api/docs/pricing)。

## 数据与测试

Research Design 页可编辑 Claim、H1–H3、角色提示、10 条合成记忆、情境库和编码规则。每条试次保存不可变的当次配置快照、角色 Prompt、编码 Prompt、机器编码与可选人工复核。旧版 SQLite 试次保持原样可读；旧记录缺少的 Provider 字段在跨模型分析时按 OpenAI 兼容解释。CSV/JSON 可导出。Human Ground Truth 五列 CSV 仍独立存放，焦虑分数不进入角色提示。

```cmd
python -m unittest discover -s tests -v
```

测试不使用真实密钥、不调用付费 API。真实五家连接、账号可用模型、账单金额和人类拟合仍需后续验证。模型重复调用不是独立人类参与者；小样本结果仅做探索性描述。
