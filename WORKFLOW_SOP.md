# EchoMind 工作 SOP

版本：1.0，2026-11-23。這是現在開始採用的工作流程；不把既有探索性實驗追認為預註冊研究。

## 每次開始先看這裡

唯一日常工作入口是本文件所在的 `repository/`。外層 EchoMind、Desktop 舊副本和 `sync-staging/` 作為歷史來源，不在多個位置同步修改同一功能。既有 `experiments/` 保持凍結；本次沒有搬動、刪除或重新生成歷史資料。

工作分成兩條：**審查既有資料**，或**設計新的實驗**。現在優先完成既有資料審查。研究者決定問題、納入規則與下一步；AI 可以查核、編程與提出解釋，但不得自行把新猜想變成正式實驗或改寫研究目標。

## 檔案放在哪裡

以下均以 `repository/` 為相對根目錄；新資料用新路徑，歷史例外保留原位。

| 類型 | 固定位置 | 編輯與版本規則 |
|---|---|---|
| 工作總流程 | `WORKFLOW_SOP.md` | 規則變動改版本，記錄原因 |
| 歷史實驗索引、完整性清單 | `configs/experiments.json`、`configs/snapshot-integrity.json` | 不改雜湊來掩蓋快照變動 |
| 新研究方案、分析計畫、決策紀錄 | `studies/<study-id>/` | 從 `templates/` 複製；公開版不含受限題目、個人資料或私有分割資訊 |
| 新的實驗實作 | `studies/<study-id>/implementation/` | 版本化；獨立程序載入，不混用各快照同名模組 |
| 可重跑的分析程式 | `analysis/<analysis-id>/` | 固定輸入、納入規則、環境與輸出路徑；不靠手改 notebook 結果 |
| 新取得的外部原始資料、授權與來源 | `data/local/external/<dataset-id>/` | 原檔保留；記錄來源、日期、SHA-256、使用條件 |
| 新實驗原始資料 | `data/local/raw/<run-id>/` | 進行中的資料庫可由 runner 寫入；結束後用 SQLite backup 固定快照，保留失敗、請求和完整原文 |
| 中間資料 | `data/local/interim/<analysis-id>/` | 程式衍生，可重新產生；修正另開版本 |
| 最終分析資料及內部圖表 | `data/local/processed/<analysis-id>/` | 連結輸入與審查版本；不覆寫舊分析 |
| 恢復的審計用資料副本 | `data/local/derived/<recovery-id>/` | 附 provenance 與 manifest；不能當成新增實驗或直接送回 runner |
| 每項審計的任務、報告和決策快照 | `data/local/audits/<audit-id>/` | `tasks.csv`、`reports/`、`decisions/`；每項任務有明確狀態與依據 |
| 審查工作台的運行紀錄 | `private_exports/data-audit/` | `reviews.sqlite3` 追加歷次決策；每次 inventory 保留版本，`inventory.json` 僅是最新版入口 |
| 經核對可公開的聚合圖表、稿件 | `reports/<analysis-id>/`、`paper/` | 先檢查資料使用條件與隱私；表格須能追溯到程式輸出 |
| 文獻 PDF | `papers/` | 本地保存；文獻筆記可公開，但不夾帶受限全文 |
| API key、私有分割 salt | 本地 `.env`、`private_inputs/` | 不進 Git、不寫到提示或公開日誌 |
| 本地備份 | `data/local/backups/` | SQLite 用 backup API；同一磁碟備份不能代替外部備份 |

目前的歷史例外：`data/pilot.sqlite3` 是舊工作台主庫；v0.3/v0.4 在各自 `experiments/.../data/`，RR 在各自 `data/` 或 `private_exports/`；人類原檔是 `human-analysis/data/raw/rr.csv`。不為了美觀搬動它們。審查報告引用原路徑與資料雜湊即可。

`data/local/`、`private_inputs/`、`private_exports/`、資料庫、原始個人資料不進 Git。Git 保存程式、方案、資料字典、測試與可公開的聚合報告。ignore 規則不會自動移除已被追蹤的檔案，提交前仍要檢查。

## A．現在怎樣審計既有資料

### A1．開一項有限範圍的審計

目前已建立 `EM-AUDIT-002`。從 repository 執行：

```powershell
python research_ops.py init-audit EM-AUDIT-003
python data_audit.py
```

第一條只在開新審計時用，不要重複建立 EM-AUDIT-002。第二條開啟 `http://127.0.0.1:8770/`。也可以雙擊 `start_data_audit_windows.bat`。預設只盤點整合倉庫；若專門核對外層歷史副本，明確使用 `--base ..`，在報告中註明範圍。

進入 `data/local/audits/<audit-id>/tasks.csv`，寫清楚本次只審哪個協議／批次。不要一次宣稱全專案「審計完成」。

### A2．先分母，再解讀效果

對每個批次記錄以下數字；未知就填 unknown，不用觀測數推測計畫數。

| 數字 | 從哪裡核對 |
|---|---|
| 計畫的決策格／episodes | 原始 config、settings 中 job、batches、schedule |
| 實際建立的 trials／episodes | trials、episodes 表 |
| 完成、失敗、進行中 | 狀態欄及完整原文，不僅看 complete |
| 未開始、缺失與重複 | 計畫鍵與實際鍵逐格比對；不靠總數相等判斷完整 |
| 角色生成、記憶取得、編碼、重試的呼叫數 | requests 或 acquisition_call_events；與決策筆數分開 |
| 可編碼的解釋／行動 | 各自合法類別的分母；缺失、unclear、other 單列 |

主庫刪掉的記錄已在 `data/local/derived/recovery-20261123/` 建立 **trial-only 審計副本**。它合併主庫與清理前備份、去除相同 ID 副本、遇衝突即拒絕；原始庫不變。設定、jobs、快照和呼叫簿仍要回原資料庫查，不能把這個副本當成可繼續實驗的主庫。

### A3．逐筆核對，審查決策另存

在工作台選來源 → 表 → 批次／trial ID → 原始列。查提示、原文、編碼理由和錯誤。每條決策寫審查者、納入／排除／待確認、原文依據及理由。先審一個小批次，修訂 codebook 後固定版本，再擴大範圍。

工作台揭示條件，是**揭盲審查**。正式盲編碼須另匯出隨機 review ID 的情境與待編文本，不附條件、模型、原編碼及映射。映射另存 private_inputs/；由獨立編碼者按同一 codebook 編碼，報告一致性及分歧裁決。回答可能自行透露記憶，須承認盲法限制；一人重看不能冒充兩名獨立編碼員。

舊 UI 的 review 現在寫入同目錄 `<database-stem>-reviews.sqlite3` 的 `review_events`，不再改寫 trials.payload；它只在當次回應返回註記。新審查統一使用 8770，避免分散在舊 UI；如過去用了舊 UI，將 sidecar 的歷史事件列入審計，不能悄悄覆蓋或當作 primary machine coding。

### A4．標明觀測依賴和配對

一列 API 回答是觀測，不自動等於獨立樣本。同一 memory snapshot 的多情境分支共享背景；RR 的多個 item 嵌套在 episode，同一 item 跨 episodes 重複。隔離版的 batched episode 與 isolated episode 粒度不同。建模／重抽樣需尊重這些群組，不能把所有 rating 當獨立人。

配對先寫出科學理由及原始鍵，再建 `pairing.csv`：pair_id、left_id、right_id、block_id、reason、missing_side。不能只因兩筆都叫 repeat_01 就宣稱同一受試者配對；缺一側保留缺失，不重跑補出想要的答案。

### A5．固定審查版本與下一步

```powershell
python research_ops.py freeze-reviews --audit-id EM-AUDIT-002 --version v1
```

這會保存完整事件、每個來源列的最新決策，以及來源是否改變／不可用。無人工審查的列仍然是未審；來源過期的決策要重新查核。不同檔案的同 ID 決策不自動互相套用。這個匯出不是最終分析樣本。

在 reports/ 寫：可確認的事實、尚未確認的問題、納入排除規則、剩餘風險、下一項具體決策。只有 tasks.csv 所列工作都有依據才關閉該審計。

## B．新實驗的最小研究設計

先從 `templates/protocol.md` 和 `templates/analysis-plan.md` 建立新 study，不修改歷史 experiments/。

1. **問題與主張**：只選一個主要問題；例如記憶條件是否改變威脅歸因，或個人化 agent 能否預測同一人的未見回答。記憶誘發負面文本不等於證明人類心理狀態。
2. **操作化與對照**：定義 construct、操弄、主要指標及對照。解釋、公開言語、預定行動分開；預定行動不能稱已發生行為。RR 相似度與自由回答編碼分開。
3. **群組與隨機化**：寫明 experimental unit、觀測單位、分派／順序隨機化、共享 snapshot、item/episode 群組、配對鍵。處理順序與情境特徵的混淆。
4. **樣本與停止規則**：預先固定情境數、每格重複、模型數、失敗處理、預算與停止條件。正式檢驗用有依據的最小效果／精度與功效分析，不把隨手跑的 n 當充足樣本。
5. **測量與分析**：固定 codebook、主要／次要結果、合法分母、排除標準、缺失處理、主要比較、多重比較策略、不確定區間和群組處理。先用合成資料驗證程式。
6. **Goal B 的人類驗證**：按 participant 分割；建 agent 的資訊與評估目標隔離，同一人的重複記錄不能跨 train/test 洩漏。建模可用的 profile／歷史資訊逐欄列許可清單，不放評估情境答案及評估量表結果。預先比較無個人化、群體基線、相同模型及資訊量控制；固定 unseen-item 預測、個體辨識／匹配及重測穩定性等評估。最低成功門檻由 protocol 事前具體量化，不能事後挑好看的指標。
7. **固定後再執行**：protocol、刺激、prompt、codebook、模型設定、程式版本、計畫格、分析方案各有版本或雜湊。若要正式預註冊，使用時間戳註冊平台；本地寫個文件不等於已註冊。

正式材料使用英文；既有中文資料保留原文。翻譯、改 prompt、換 coder 或重跑都建立新版本，記錄偏離原因，不回填舊資料冒充原方案。

人類 RR 的既有 held-out 已查看，標記為 exposed/exploratory。不可藉重新命名、換 salt 或重分同一批已看結果恢復其未接觸性。確認性研究另留合適的未查看資料；必要時另採樣並遵循研究審查與參與者同意程序。

## C．執行、分析、寫作與備份

執行前固定 run_id 與 `templates/run-manifest.json`；把 Git HEAD **及 dirty diff**、Python／依賴環境、隨機種子、請求與回傳模型、參數、輸入與方案雜湊放到本地 run 目錄。模型版本未知就記未知；不要把順序 seed 當作模型 seed。模型支援、價格與預算在當次執行前另查官方來源。

新 runner 必須明確把輸出寫入 raw/<run-id>/；建立資料夾本身不會重新導向舊 runner。歷史 runner 仍按舊固定路徑工作；除非已經適配並測試，不要從凍結目錄開新實驗。實驗權限不由本 SOP 自動授予。

執行後核對計畫格與結果格、保留失敗和重試、固定資料快照。檔案雜湊不代替 SQLite 的一致性快照；活躍 WAL 的資料庫不能只複製主檔。`recovery-manifest.json` 是衍生審計視圖的追溯紀錄，不是全庫備份。

分析前：選唯一來源／批次、固定審查版本、建立 derived dataset，保留 source_id → review_id → analysis_row_id 的映射。先驗證缺失與分母，再看效果；原始 machine coding 與人工重編分開報告。現有 analysis.py 會拒絕跨批次／協議／prompt／coder 等不相容資料直接混算。

寫作同步進行：先寫問題、方法及偏離紀錄；結果每張表附 analysis_id、輸入版本、程式與輸出路徑。把已觀察結果產生的新假設標作探索，不重寫成事前假設。效果沒出現、解析失敗或對照失敗都可以是結果，不能只保留支持預期的輸出。

每日收工：更新 decision-log 的一行（完成什麼／依據／未解問題／下一步），保存 Git diff，確認新資料有本地備份。每週做一次獨立裝置或合適的持久儲存備份並抽查還原；本次尚未建立外部備份。提交前執行：

```powershell
git status --short
python scripts/run_checks.py --snapshots
git diff --check
```

允許 localhost 時再加 `--http`；環境阻擋必須記錄，不把未跑測試寫成通過。公開前另檢查輸出、權限與同意範圍。此 SOP 沒有自動發布、推送、上傳或發送任何資料。

## 啟動位置與定期清理

目前程式在 Documents/ChatGPT/EchoMind/repository/，桌面的舊副本不會自動同步。
修正版 start_data_review.bat 會先檢查相鄰的程式，再找上述固定入口，使用完整路徑啟動；
找不到時停止並顯示錯誤，不會留在錯誤目錄繼續執行 Python。它也可以複製到桌面使用。

清理預覽：`powershell -File scripts/cleanup_workspace.ps1 -WhatIf`。
實際清理：`powershell -File scripts/cleanup_workspace.ps1`。
工具只清除列明的可重建快取；sync-staging 若存在，先存到 data/local/backups/cleanup-<time>/，
逐檔核對 ZIP 與原檔 SHA-256 後才移除散落暫存檔。資料庫、歷史實驗、原始輸出、
文獻、先前備份與審查決策不在刪除清單。路徑超出工作區或遇到連結／junction 時拒絕。
不因為檔案舊、名稱含 mock/error、或與新版重複，就刪除科學證據。

## 參考與採用方式

這些是流程參考，不是 EchoMind 已具備效度的證明。查閱日期：2026-11-23。

| 原始來源 | 本專案採用的做法 |
|---|---|
| [Cookiecutter Data Science：Opinions](https://cookiecutter-data-science.drivendata.org/opinions/) | 保留 raw，經 interim 到 processed；程式可追溯再現，資料與程式版本管理分開 |
| [Wilson et al. 2017, Good enough practices in scientific computing](https://doi.org/10.1371/journal.pcbi.1005510) | 採足夠簡單的專案組織、原始資料保存、版本控制、文件和可恢復備份 |
| [COS：Preregistration](https://www.cos.io/initiatives/prereg) | 預先固定計畫，區分已看資料的探索與未看資料的確認；既有資料研究誠實揭露先前接觸 |
| [Stanford CRFM：HELM 文件](https://crfm-helm.readthedocs.io/en/latest/) | 執行、彙總、檢視原始提示／回答分開。只借鑑結構，沒有安裝或遷移到 HELM |

上述目錄名稱、ID 規則、每次審計任務和關閉條件是為 EchoMind 設計的本地約定，不是來源要求的通用標準。下一步先完成 EM-AUDIT-002 的一個批次，再決定是否開始新研究。
