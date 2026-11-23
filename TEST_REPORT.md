# EchoMind 测试报告

## Memory Acquisition MVP v0.2（2026-10-23）

EchoMind 独立项目最终全套 **81 项测试通过，47.258 秒**。新增获取协议浏览器验收、原来源对照 v2 验收与原历史页验收均通过。所有自动化使用临时库／注入假 transport，无真实付费调用；Gate 3 的单测仅模拟 transport，不代表真实 Provider smoke。

另明确保存一批 `MOCK_NOT_LLM` 演示：84 条决策、21 份快照、180 次模拟请求／360 条审计事件、0 次真实 API。原 446 条历史记录和原配置逐条保持一致，当前主库为 530 条、17 批。新表为 `acquisition_snapshots` 与 `acquisition_call_events`，建表前已用 SQLite backup API 备份。

最终代码指纹 `72a7512284f93b90`；实际服务为 `http://127.0.0.1:8769/#acquisition`，读取 `EchoMind/data/pilot.sqlite3`。详细证据见 `data/acquisition-v02-verification.json`，结果与说明见 [MVP_IMPLEMENTATION_REPORT.md](MVP_IMPLEMENTATION_REPORT.md)。下文保留此前验收的历史记录。

## EchoMind 独立目录验证（2026-10-22）

本节针对 `<repo-root>`。当前地址 `http://127.0.0.1:8769/`，以离线模式运行，实际数据库为本目录 `data/pilot.sqlite3`；原 SOS 及其 8768 服务保留。以下旧报告的路径和版本为当时的历史证据。

- `python -m unittest discover -s tests -v`：**61 项通过**，20.288 秒。包括原有 57 项及 4 项启动隔离回归测试，验证其他目录／数据库／版本／模式不可误开、继承旧数据库环境变量时仍固定使用本目录，以及两个离线开关均能禁止调用。输出保存在 `data/echomind-unittest.txt`。
- `node tests/browser_measurement_smoke.mjs`：通过。新目录的临时数据库运行 8 + 192 条 MOCK，验证预览、刷新恢复、多维编码、历史与导出，以及桌面和手机布局；无 JavaScript 异常。
- `node tests/browser_research_smoke.mjs`：通过。仅在正式数据库的一致性临时副本中验证 446 条／16 批历史、A 60 条、B 24 条、失败与协议筛选、实际 Prompt、重复导入、版本保存及桌面／手机界面。
- 默认端口改为 8769 后重跑 4 项启动隔离测试，全部通过；再连接实际健康检查，验证启动器认可当前 EchoMind 目录、数据库、版本与离线模式。
- 两个正式数据库的四张表逐行 SHA-256 均与迁移快照一致，完整性检查均为 `ok`。本次没有向正式库加入 MOCK 或真实实验记录，也没有调用真实模型 API。

当前服务代码指纹：`f9d7110dc63cd86b`。机器可读结果：`data/echomind-verification.json`；复制清单与之前的 EchoMind 源码备份见 [ECHOMIND_MIGRATION.md](ECHOMIND_MIGRATION.md)。

## 2026-10-22 来源对照 v2 增量验收

当前已将原 A/B 提示接入独立 `memory-source-v2` 运行流程。下面 2026-10-21 的段落保留当时的交付状态；其中“新提示尚未接入”已由本轮完成，心理测量与人工验证仍未完成。

| 验证 | 本轮结果 |
|---|---|
| Python 回归 | **57 项通过**，含新增 11 项；最终运行 20.272 秒 |
| 新协议浏览器 | 临时库完成 8 + 192 条 MOCK；64 份不同提示、16 个分层；配置改动使预览失效、运行中刷新并从服务器找回任务、导出／盲评表／历史接入通过；桌面和 390px 手机布局无溢出、无 JS 异常 |
| 历史浏览器 | 主库只读副本 446 条／16 批次；原 A 60、B 24、失败筛选、重复导入、提示保存与刷新通过 |
| 正式库完整性 | 修改前 446 条全部 payload SHA256 一致；新增 0、删除 0、改写 0；integrity_check=ok |
| 当前服务 | 8768，offline=true，代码指纹 a82d700c1a65b038；来源协议 bootstrap、页面、JS/CSS 和新教程 HTTP 200；主库尚无来源 v2 批次 |

新增覆盖：完整四组与逐字匹配材料；192 条规划；版本／身份改变后的预览校验；已保存提示实际用于生成；编码器输入不含材料；新版结构定义与旧版隔离；假传输中的成功／认证失败／编造引文；失败原文留存与未知分母；多维共存及条件性行动；旧 payload 不变；协议隔离；完整 CSV/JSON；盲评映射；进程重启。

验证中修正了：旧测试固定等待 0.3 秒后清理临时库的同步问题，改为等待任务终止；新编码器不能沿用旧 OpenAI JSON Schema；浏览器刷新测试须在服务接受任务后进行，同时增加从服务器恢复任务 ID 的路径；历史页新增中文文本写入时的编码问题。旧历史浏览器的批次数改为读取初始副本清单，避免其他批次增加导致硬编码失效。

证据文件：`data/source-v2-verification.json`（备份与哈希）、`data/source-v2-browser-result.json`、`data/source-v2-setup.png`、`data/source-v2-results.png`、`data/source-v2-mobile.png`。MOCK 中四组使用相同分布，D=0 是预设流程检查，不是研究发现。所有模拟／假传输记录均在临时库；未打开真实凭据，未调用付费 API。

运行：`python -m unittest discover -s tests -v`、`node tests/browser_measurement_smoke.mjs`、`node tests/browser_research_smoke.mjs`，先设置 `SOS_OFFLINE=1`。使用方法见 [SOURCE_MEASUREMENT_V2.md](SOURCE_MEASUREMENT_V2.md)。

仍需完成的研究工作：双人盲评与一致性检验、材料独立评定、封存新评估情境、真实模型及跨模型检验。人工回导／一致性页面尚未实现。本轮完成的是可运行的研究流程，不是心理 claim 的验证。

## 2026-10-21 历史审计验收

日期：2026-10-21。实际验证环境：Python 3.11.8、Node 24.15.0、Windows Edge。所有模型验证使用 MOCK 或注入的假传输；HTTP 测试使用临时数据库，浏览器历史验收使用主库的只读 SQLite 备份副本。未调用付费模型，未打开 `.env`。

## 结果

| 验证 | 结果 |
|---|---|
| Python 自动测试 | 46 项通过：原 33 项 + 新 13 项 |
| 历史浏览器验收 | 422 条/15 批次可见；A 60、B 24；失败/协议筛选、实际 Prompt/原文展开、并列对照、重复导入、版本保存与刷新、桌面/390px 移动布局通过，无 JS 异常 |
| 旧机制浏览器验收 | 临时库完成 60 条 MOCK；三通道、缺省行为、固定提示、比例、来源门槛、批次导出、刷新、无效次数拦截与桌面/移动布局通过 |
| 真实主库只读复核 | 最终快照 446 条/16 批次；integrity_check=ok；初始 362 条 payload 的逐条 SHA256 全部一致；审计期间另外新增的 60+24 条单列保留 |
| 本地正式入口 | 8768 已以 offline=true 启动；health 显示项目内主库绝对路径；历史 API 读取 446 条/16 批次；不允许真实模型调用 |
| 原导出交叉验证 | DeepSeek A 导出 60/60、MiniMax 导出 60/60 与主库逐字段一致 |
| 新提示 | A/B 模板与条件盲输入构造、不可覆盖版本、重启后读取、修改 coder 需新版本、证据逐字回指验证通过；没有测试模型心理效度 |

浏览器截图：`data/research-history-desktop.png`、`data/research-history-mobile.png`、`data/demo-mechanism-desktop.png`、`data/demo-mechanism-mobile.png`。历史截图显示临时副本的绝对路径，正式服务应显示项目内主库路径。

## 新回归测试覆盖

`tests/test_research_repair.py` 覆盖：

- 从不同 cwd 打开同一项目相对数据库；关闭重开 Store 后记录完整。
- 导入前预览无写入；提交前备份；保留未知字段与原错误；重复导入为 0；同 ID 冲突整份拒绝；非法文件、凭据字段、校验错误、NaN 和重复键拒绝。
- 原始 JSON 保留 64 位随机种子和浮点表示，防止浏览器解析造成不可逆舍入。
- 历史跨协议/模型/来源/日期/状态筛选，失败不进入有效分母；即便同批混合配置也分格，原报告不能混协议生成。
- HTTP 导入、JSON/CSV 完整导出、单批导出、MOCK 任务、提示版本保存和进程重启后的读取。
- 认证失败单线程仅发出 1 个试次；限流假传输最多 3 次尝试后停止批次；连续 3 条失败停止；并发时最多 3 条已发出的试次可完成，不再补发。
- 未结束任务在重启后标为 interrupted，原 trial 不重写、不自动付费重跑；归档任务可重新访问。
- 离线模式在读取凭据之前拦截真实调用；假 transport 不读取真实密钥。
- 不利归因引文与非不利归因引文分开；编造“对方忙”但原文不存在时验证失败。

## 测试中发现并修复的问题

1. SQLite connection 的上下文管理不自动 close，最初备份测试在 Windows 清理临时文件时锁定文件。已显式 closing 备份连接，重测通过。
2. 浏览器最初 JSON.parse→stringify 导入会舍入大整数种子并改变浮点表示，导致合法历史导出哈希不一致。改为发送原始文件文字，在服务器严格解析；真实 A 的 60 条重复导入验收通过。
3. 页面合并后旧浏览器测试的全页 `.condition` 选择器把消融组也计入，7 不等于 3。改为机制 panel 内选择器，保持其三组验收。
4. 初始验收硬编码主库 362 条；期间出现额外真实批次。测试改为以只读副本初始清单为基准，同时必须包含原 A/B；新批次未删除。浏览器验收副本为当时 422 条/15 批次；之后又出现 24 条，最终主库只读核查为 446 条/16 批次。这 84 条不是本轮离线测试生成的数据，未混入原 A/B 的科研分析。

## 运行方式

在本目录 PowerShell：

```powershell
$env:SOS_OFFLINE = '1'
python -m unittest discover -s tests -v
node tests/browser_research_smoke.mjs
node tests/browser_mechanism_smoke.mjs
python tests/recovery_audit.py
python server.py --offline --port 8768
```

`browser_research_smoke.mjs` 默认 Python 为 `C:\Program Files\Python311\python.exe`，可用 `SOS_TEST_PYTHON` 指向别处；需要 Node 22+ 与已安装 Edge。浏览器只使用新建临时 profile，不访问日常浏览器的 Cookies、登录或历史。

`tests/recovery_audit.py` 只读正式主库，并写独立审计导出与空白人工复核表；不会导入任何记录或调用模型。它依赖本次 `data/recovery-before.json` 清单，不是通用空项目的 CI 测试。新测试文件均使用临时库。

使用 `start_audit_windows.bat` 可在离线模式打开工作台。普通启动仍由用户自行选择。健康接口 `/api/health` 给出解析后的数据库路径、offline 状态及代码指纹。源码更新后重启服务，刷新网页才能使用新的后端；启动器会识别本轮之后的指纹差异。

## 尚未解决或未声称完成的事项

- 新 codebook 没有得到两名真实编码员的一致性验证；空白 84 条复核表不是人工数据。
- 新提示只实现版本管理、比较、离线预览和校验；新协议尚未接入运行器，未进行付费试验或人类有效性验证。
- 未做跨模型、跨情境正式复现或功效保证；所有旧研究局限保留在 PROMPT_AUDIT.md。
- 旧状态页和旧记忆页仍保留历史术语、不同分母/人工复核行为；统一历史视图明确标注其差异，没有为统一而重算历史。
- 早期没有保存的进程队列元数据及未返回的模型输出不能恢复。原始 payload 保留不代表供应商全部 HTTP 报文被保存过。
- 自动化通过说明数据流程可运行，不说明心理学 claim 已成立。EchoMind 远程仓库仅审阅，本地测试通过不等于对远端提交运行了同样测试。
