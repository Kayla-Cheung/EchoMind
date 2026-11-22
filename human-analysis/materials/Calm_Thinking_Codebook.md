# Eberle et al. (2024) Calm Thinking — 研究 Codebook 與材料手冊

本文件彙整 Eberle et al. (2024) "Calm Thinking"（網絡認知偏誤修正 CBM-I 隨機對照試驗）中 **Recognition Ratings (RR, 認知再認評分)** 任務的實驗材料、變量結構與編碼說明。

---

## 1. 研究背景與測量範式

- **研究來源**：Eberle, J. W., et al. (2024). Web-based Cognitive Bias Modification for Interpretation (Calm Thinking Study).
- **測量工具**：Recognition Ratings (RR) 任務，用於測量參與者在模糊情境中的解釋偏誤（Interpretation Bias）。
- **數據集文件**：`rr.csv`
- **數據維度**：3,259 筆觀測值（Observations），45 個變量（Variables），涵蓋 1,524 位獨立參與者（Participants）。

---

## 2. 行（Row）與觀測（Observation）的層次概念

在 `rr.csv` 中：
- **一行（Row）不代表一名單獨的參與者，而是代表「某參與者在某個時間節點的一次測量（Participant × Session Observation）」**。
- **Participant ID 欄位**：`participant_id`（整數 ID，全數據集共 1,524 位獨立受試者）。
- **測量次數**：研究包含四個時間點（`session_only`），同一位受試者最多在不同 Session 出現 4 次：
  - `preTest`：基線前測（Baseline），共 1,524 筆。
  - `thirdSession`：第三次干預時段，共 693 筆。
  - `fifthSession`：第五次干預時段，共 558 筆。
  - `PostFollowUp`：干預結束後追蹤，共 484 筆。
  - 總計：$1,524 + 693 + 558 + 484 = 3,259$ 行。無重複的受試者×階段組合（0 duplicate person-session rows）。

---

## 3. 欄位（Columns）與變量說明

全表共有 45 個欄位：

### 3.1 基礎元數據欄位（6 欄）
1. `X`：原始 R 導出索引號（列序號）。
2. `id`：該次測量記錄的唯一資料庫主鍵（Database Record ID）。
3. `participant_id`：受試者唯一編號（Participant Identifier）。
4. `session_only`：測量階段（`preTest`, `thirdSession`, `fifthSession`, `PostFollowUp`）。
5. `date`：測量完成的本機記錄日期時間字串。
6. `time_on_page`：受試者在該評分頁面停留的時間（秒）。

### 3.2 評分欄位（36 欄 = 9 情境 × 4 解釋）
涵蓋 9 個模糊日常情境，每個情境評估 4 種類型的解釋：
- `_ns`：**Negative Threat-Specific**（負面威脅特定解釋，核心指標）
- `_ps`：**Positive Threat-Specific**（正面威脅特定解釋，核心指標）
- `_nf`：**Negative Filler / Threat-General**（負面非威脅填充題）
- `_pf`：**Positive Filler / Threat-General**（正面非威脅填充題）

### 3.3 時間戳欄位（3 欄）
43. `date_as_POSIXct`：POSIXct 格式的標準時間。
44. `system_date_time_earliest`：系統記錄最早時間戳。
45. `system_date_time_latest`：系統記錄最晚時間戳。

---

## 4. 評分量表與心理學意義

### 評分尺規（1–4 分 Likert Scale）
受試者閱讀情境後，對每一種解釋出現的可能性或相似程度進行評分：
- **1** = Very unlike what I was thinking（非常不符合我的想法）
- **2** = Somewhat unlike what I was thinking（有些不符合我的想法）
- **3** = Somewhat like what I was thinking（有些符合我的想法）
- **4** = Very like what I was thinking（非常符合我的想法）

### 缺失值特殊編碼
- **555** = **Missing / Skipped / Prefer not to answer**（受試者跳過或拒絕回答）。
- 全表 36 個評分欄中共有 761 個評分單元格值為 `555`。
- **重要提醒**：在進入統計計算（如均值、相關性、Cronbach's $\alpha$）之前，必須將 `555` 替換為 `NaN` 或進行專門過濾，切勿將其視為數值 555 參與均值運算！

### 科研邊界警示
- Calm Thinking 測量的是**「語義相似度與情境解釋傾向（Semantic & Situational Interpretation Likelihood）」**。
- **嚴禁**擅自將本評分直接等同於臨床診斷、社交焦慮評級或人際拒絕預期分數。

---

## 5. 9 個情境與 36 項解釋選項完整對照表

| 情境代號 | 欄位後綴 | 變量名 | 完整解釋選項文本（English Prompt） |
| :--- | :--- | :--- | :--- |
| **blood_test** | `_ns` | `blood_test_ns` | And you think that you will not be able to stand your anxiety while you wait. |
| (抽血化驗) | `_ps` | `blood_test_ps` | And you know that you can handle your anxiety while you wait. |
| | `_nf` | `blood_test_nf` | And you are annoyed because your doctor is not very friendly. |
| | `_pf` | `blood_test_pf` | And you think about how nice your doctor is. |
| **elevator** | `_ns` | `elevator_ns` | You think that the elevator will probably break down while you are on it. |
| (乘搭電梯) | `_ps` | `elevator_ps` | You think that riding the elevator will be safe. |
| | `_nf` | `elevator_nf` | You think about how smelly the lobby is. |
| | `_pf` | `elevator_pf` | You think that you are going to like your friend’s new apartment. |
| **job** | `_ns` | `job_ns` | And worry about becoming broke. |
| (工作變動) | `_ps` | `job_ps` | And know that you can rely on your savings. |
| | `_nf` | `job_nf` | And are sad about leaving your current coworkers. |
| | `_pf` | `job_pf` | And are excited about not having to set an alarm. |
| **lunch** | `_ns` | `lunch_ns` | Because she thinks you are a slob. |
| (共進午餐) | `_ps` | `lunch_ps` | Because she is paying attention as you describe your weekend plans. |
| | `_nf` | `lunch_nf` | And you frown because you forgot to bring water to lunch. |
| | `_pf` | `lunch_pf` | And you smile because your lunch tastes good. |
| **meeting_friend**| `_ns` | `meeting_friend_ns` | Think your friend decided she did not want to see you. |
| (相約會面) | `_ps` | `meeting_friend_ps` | Get a call from your friend who is on her way, but running late. |
| | `_nf` | `meeting_friend_nf` | Notice the bar smells gross. |
| | `_pf` | `meeting_friend_pf` | Order your favorite snack. |
| **noise** | `_ns` | `noise_ns` | You feel afraid, and worry that you cannot handle the fear. |
| (屋內異響) | `_ps` | `noise_ps` | You feel afraid, but you know that you can tolerate the feeling. |
| | `_nf` | `noise_nf` | You feel cold, and think about how the house needs better heating. |
| | `_pf` | `noise_pf` | You feel happy, and think about how lovely your house is. |
| **scrape** | `_ns` | `scrape_ns` | And you think it will probably get seriously infected. |
| (擦傷膝蓋) | `_ps` | `scrape_ps` | But you know you will be okay. |
| | `_nf` | `scrape_nf` | And you are frustrated because you tore your shorts. |
| | `_pf` | `scrape_pf` | But you are happy that you are getting exercise. |
| **shopping** | `_ns` | `shopping_ns` | And think you are probably coming down with the strange illness. |
| (商場購物) | `_ps` | `shopping_ps` | And think you are unlikely to catch the strange illness. |
| | `_nf` | `shopping_nf` | And feel bored of shopping. |
| | `_pf` | `shopping_pf` | And smile because you enjoy shopping. |
| **wedding** | `_ns` | `wedding_ns` | People in the audience find your efforts laughable. |
| (婚禮致辭) | `_ps` | `wedding_ps` | People in the audience laugh in appreciation. |
| | `_nf` | `wedding_nf` | You notice someone you do not like just walked into the reception. |
| | `_pf` | `wedding_pf` | You notice a friend you were hoping to see walk into the reception. |

---

## 6. 既有數據核驗基準（來自 data-verification.json）

- **Shape**：3259 rows × 45 columns
- **總評分單元格（Rating Cells）**：$3259 \times 36 = 117,324$
- **取值分佈（Value Counts）**：
  - 1 分：35,686 次
  - 2 分：31,504 次
  - 3 分：32,356 次
  - 4 分：17,017 次
  - 555（缺失）：761 次
- **基線內部一致性（Cronbach's $\alpha$ on preTest Complete Cases）**：
  - Negative Threat-Specific (`ns`, $N=1501$): $\alpha \approx 0.7587$
  - Positive Threat-Specific (`ps`, $N=1499$): $\alpha \approx 0.7178$
