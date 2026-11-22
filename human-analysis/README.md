# EchoMind · 數據分析工作台 (EchoMind-analysis)

本項目為 EchoMind 科研專案設立之獨立 Python 數據分析環境，專門用於心理學認知實驗數據（Eberle et al., 2024 Calm Thinking 數據集）的探索性分析、結構解讀，以及後續轉換為 LLM Benchmark 的研究工作。

---

## 一、目錄結構說明

```text
EchoMind-analysis/
│
├── data/
│   ├── raw/                  # 原始研究數據存檔（唯讀，禁止覆蓋或直接清洗）
│   │   ├── rr.csv            # Calm Thinking Recognition Ratings 任務原始數據
│   │   └── README.md
│   └── processed/            # 將來僅存放清洗、標準化後的衍生數據
│       └── .gitkeep
│
├── materials/                # 原始研究材料與元數據
│   ├── Calm_Thinking_Codebook.md   # 完整實驗設計、變量對照表與評分尺規手冊
│   ├── calm-variable-map.json      # 36 項解釋評分與原始英文 Prompt 映射表
│   └── data-verification.json      # 先前審計核驗基準（驗證維度、Alpha、取值分佈）
│
├── notebooks/                # Jupyter 分析筆記本
│   └── 01_data_exploration.ipynb   # 第一階段：數據讀取與結構認識（繁體中文註解）
│
├── figures/                  # 後續統計分析圖表導出目錄
│   └── .gitkeep
│
├── copy_data.bat             # 一鍵數據複製與 SHA-256 核驗批處理腳本
├── environment.yml           # Conda 依賴環境重現配置檔
└── README.md                 # 專案說明文件（本文件）
```

---

## 二、數據來源與研究背景

- **研究來源**：Eberle, J. W., et al. (2024). *Calm Thinking Study* (Cognitive Bias Modification for Interpretation, CBM-I).
- **任務類型**：Recognition Ratings (RR) 任務，測量受試者在模糊社交與日常情境下的解釋偏誤傾向。
- **數據集規模**：3,259 行（Observations）× 45 列（Variables），包含 1,524 位獨立受試者（Participants）。
- **情境數量**：9 個模糊情境（抽血、電梯、工作、午餐、會友、異響、擦傷、購物、婚禮）。
- **評分變量**：36 個評分欄位（包含負面特定 `_ns`、正面特定 `_ps`、負面填充 `_nf`、正面填充 `_pf`）。
- **缺失值標記**：`555`（跳過／拒絕回答，非真實評分，進入統計前須轉為 `NaN`）。

---

## 三、環境啟動與使用指南

### 1. 推薦使用之 Python / Conda 環境
電腦中已安裝 Anaconda。目前已存在具備完整科學計算套件之環境：
- **推薦環境 1（現有 Anaconda Base 環境）**：
  - Python 版本：`3.13.9`
  - 內置套件：Pandas 2.3.3, NumPy 2.3.5, Matplotlib 3.10.6, Jupyter 1.1.1, ipykernel 6.31.0, SciPy 1.16.3, Seaborn 0.13.2。
- **推薦環境 2（獨立隔離環境 `echomind-analysis`）**：
  - 若需完全依賴隔離，可在 Anaconda Prompt 中執行：
    ```bash
    conda env create -f environment.yml
    conda activate echomind-analysis
    ```

### 2. 在 VS Code 中開啟與執行步驟
1. 開啟 **VS Code**。
2. 點擊功能表 **檔案 (File) -> 開啟資料夾 (Open Folder)**。
3. 選擇桌面路徑：
   ```text
   C:\Users\Kayla\Desktop\EchoMind-analysis
   ```
4. **確認擴充套件**：
   - 確保已安裝 Microsoft 官方 **Python** 與 **Jupyter** 擴充套件（搜尋 `ms-toolsai.jupyter` 並安裝）。
5. 開啟筆記本：
   - 在左側檔案總管展開 `notebooks/`，點擊打開 **`01_data_exploration.ipynb`**。
6. **選取 Jupyter Kernel**：
   - 點擊筆記本右上角的 **「選取核心 (Select Kernel)」**。
   - 選擇 **Python Environments...** -> 選擇 `base (C:\Users\Kayla\anaconda3\python.exe)` 或新建的 `echomind-analysis`。
7. **逐個執行 Cells**：
   - 依序點擊 Cell 左側的執行按鈕（或按 `Shift + Enter`），即可看到 Pandas 讀取的真實實驗數據。

---

## 四、科研數據管理守則
1. **嚴禁修改原始研究數據**：`data/raw/` 中的數據文件保持唯讀，不作任何就地修改。
2. **清洗衍生分流**：任何處理後數據、特徵衍生或子集篩選一律輸出至 `data/processed/`。
3. **客觀科學界限**：Calm Thinking 評分代表語義相似度與解釋傾向，嚴禁擅自過度推論為臨床診斷或拒絕敏感焦慮指標。
