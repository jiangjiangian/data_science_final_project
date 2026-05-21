# CPBL Unsupervised Feature Discovery (2023 + 2024)

114-2 資料科學期末專題。從 [rebas.tw](https://github.com/rebas-tw/rebas.tw-open-data)
官方 release 取得 CPBL 中華職棒 2023 + 2024 賽季資料，建構 team-game-level
特徵，並用**非監督式學習**找出可作為 leak-free 預測因子的 cluster_id /
PC scores / GMM soft probabilities。

## 主要交付物

| 路徑 | 內容 |
|---|---|
| `Scripts/cpbl_unsupervised_feature_discovery.ipynb` | 193-cell 主 notebook：完整 7 個 stage 的程式、輸出與「結果解讀」中文評註 |
| `Results/notebook_executed.html` | 上述 notebook 的 HTML 匯出，無 Jupyter 也可瀏覽 |
| `docs/plan.md` | 本研究計畫書（goal / context / verification / risks） |
| `docs/knowledge_base/` | 從 `course-material/` 蒸餾出來的 10 份 Markdown 知識庫 |

## 目錄結構

```
.
├── README.md                                          ← 你在這裡
├── master.sh                                          ← 一鍵 rebuild
├── .gitignore
├── Data/                                              ← 原始與外部資料
│   ├── README.md
│   ├── 2023/                                              本機已有的 2023 rebas release JSONs（4 子資料夾）
│   ├── 2024/                                              佔位資料夾；notebook Stage 1 會自動從 rebas 下載
│   └── reference/                                         analyze_wang 等對照來源
├── Scripts/                                           ← 程式碼
│   ├── cpbl_unsupervised_feature_discovery.ipynb         主 notebook（已執行 + 已加註解）
│   ├── build/                                            產生 notebook 的腳本鏈
│   │   ├── README.md
│   │   ├── modify_notebook.py                                注入 3 個改動（Wang merge / pre-game gate / K consensus）
│   │   └── inject_explanations.py                            生成「結果解讀」與每 stage 小結
│   └── legacy/                                           前期工作（pre-game win prediction）
│       ├── cpbl_pregame_winprob.ipynb
│       └── figures/{clustering,eda_overview,evaluation,pca,shap}.png
├── Derived/                                           ← 中間產物，gitignored，由 master.sh 重建
│   └── (空)
├── Results/                                           ← 最終產出
│   ├── README.md
│   └── notebook_executed.html
└── docs/
    ├── plan.md                                            研究計畫書
    └── knowledge_base/                                    課程材料蒸餾出的 KB
        ├── README.md
        └── topic03_*..topic09_*.md（10 個 topic）
```

## 快速開始

### 1. 直接讀

打開 [`Results/notebook_executed.html`](Results/notebook_executed.html) 即可——
所有 7 個 stage、24 張圖、20+ 張表都已 inline 渲染好。

### 2. 在 Jupyter 重跑

```bash
./master.sh
```

`master.sh` 會：
1. 用 `jupyter nbconvert --execute` 跑完整本 notebook
2. 重新匯出 `Results/notebook_executed.html`

第一次跑會從 rebas.tw 下載三個 release zip 到 `Data/2024/`（2023 已內附）。

### 3. 從零生成 notebook

詳見 [`Scripts/build/README.md`](Scripts/build/README.md)。

## Pipeline 流程

```
Stage 0  setup           ─→ Stage 1  rebas 下載
                              │
                              ▼
Stage 2  preprocessing       team-game feature engineering
            │                ↳ 2.7a Wang 對照
            │                ↳ 2.7b pre-game lag features
            │                ↳ 2.9  pre-game / post-game gate
            ▼
Stage 3  descriptive stats
            ▼
Stage 4  EDA viz（10 張）
            ▼
Stage 5  unsupervised
            │ 5.1-5.6   filter → scale → PCA
            │ 5.7       K 共識（六方法投票）
            │ 5.8-5.11  K-Means / Ward / GMM / HDBSCAN + 穩定性
            │ 5.12-5.14 silhouette diag / UMAP / t-SNE
            │ 5.15-5.18 cluster mean / radar / notched box / SHAP
            │ 5.18a     ANOVA F + MI 重要性
            │ 5.19-5.20 跨季 shift + derived feature register
            ▼
Stage 6  synthesis（overlap、new candidates、design summary）
            ▼
Stage 7  export（DOWNLOAD_ALL flag 控制 zip 輸出）
```

## 版本控制慣例

- **進 git**：`README.md` / `master.sh` / `.gitignore` / `Scripts/` / `Results/` / `docs/` / `Data/`（純資料子集）
- **不進 git**：`Derived/` 與 `Results/figures/` `Results/tables/`（由 notebook 在 `DOWNLOAD_ALL=True` 時產生）
- 大型外部資料（如原本 199 MB 的 `course-material/` HTML 原檔）建議遷往 GitHub Release asset，不要進主 repo

## 主要參考

- [rebas.tw 開放資料](https://github.com/rebas-tw/rebas.tw-open-data) — 比賽原始 JSON
- [analyze_wang branch](https://github.com/cde52470/data_science/tree/analyze_wang) — 學長之前 supervised 預測的程式與 cleaned CSV
- 課程 `course-material/`（199 MB HTML 原檔，已移出 repo；蒸餾版見 `docs/knowledge_base/`）
- Lo et al. 2025, "Application of Machine Learning Models for Baseball Outcome Prediction"
