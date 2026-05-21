# CPBL Unsupervised Feature Discovery (2023 + 2024)

114-2 資料科學期末專題。從 [rebas.tw](https://github.com/rebas-tw/rebas.tw-open-data)
官方 release 取得 CPBL 中華職棒 2023 + 2024 賽季資料，建構 team-game-level
特徵，並用**非監督式學習**找出可作為 leak-free 預測因子的
`cluster_id` / PC scores / GMM soft probabilities。

## 主要交付物

| 路徑 | 內容 |
|---|---|
| `Scripts/cpbl_unsupervised_feature_discovery.ipynb` | 主 notebook（193 cells，7 stage，已執行 + 中文「結果解讀」評註） |
| `Results/notebook_executed.html` | 程式碼無關的 HTML 報告：Mermaid 流程圖 + per-stage 渲染輸出 + 解讀；無 Jupyter 也可開啟 |
| `Results/stage{2..6}/` | 51 個 CSV / PNG / HTML 產物，按 stage 分資料夾 |
| `docs/plan.md` | 研究計畫書（goal / context / verification / risks） |
| `docs/knowledge_base/` | 從 `course-material/` 蒸餾出來的 10 份 Markdown 知識庫 |

## 完整目錄樹

```
.
├── README.md                                                  你在這裡
├── master.sh                                                  一鍵 rebuild（執行 notebook + 重生 HTML）
├── .gitignore
│
├── Data/                                                      原始與外部資料
│   ├── README.md                                                  rebas.tw release URL / 授權 / 結構說明
│   ├── 2023/                                                      2023 rebas releases（內附；~76 MB JSON）
│   │   ├── CPBL-2023-G1-G150-OpenData/                                G1-G150 + 合併 JSON（151 檔）
│   │   ├── CPBL-2023-G151-G300-OpenData/                              G151-G300 + 合併 JSON（151 檔）
│   │   ├── CPBL-2023-Challenge-OpenData/                              季後挑戰賽（4 檔）
│   │   └── CPBL-2023-TaiwanSeries-OpenData/                           台灣大賽（8 檔）
│   ├── 2024/                                                      佔位夾；notebook Stage 1 第一次跑會自動下載 zip
│   │   └── README.md
│   └── reference/                                                 對照組（analyze_wang cleaned CSV 等）
│       └── README.md
│
├── Scripts/                                                   程式碼（版本控制）
│   ├── cpbl_unsupervised_feature_discovery.ipynb                  主 notebook（193 cells，含 inline outputs）
│   ├── build/                                                     產生 / 重建 notebook 的腳本鏈
│   │   ├── README.md                                                  pipeline 說明
│   │   ├── modify_notebook.py                                         注入 3 改動：Wang 對照 / pre-game gate / K 共識
│   │   ├── inject_explanations.py                                     生成「結果解讀」評註與 stage 小結
│   │   └── build_report_html.py                                       生成 Results/notebook_executed.html
│   └── legacy/                                                    前期工作（pre-game win prediction）
│       ├── cpbl_pregame_winprob.ipynb                                 學長舊 notebook
│       └── figures/                                                   舊 notebook 的 5 張 figure
│           ├── clustering.png
│           ├── eda_overview.png
│           ├── evaluation.png
│           ├── pca.png
│           └── shap.png
│
├── Derived/                                                   中間 artefacts；gitignored；由 master.sh 重建
│   └── (執行時才產生)
│
├── Results/                                                   最終產出（53 檔，~21 MB）
│   ├── README.md                                                  Results 結構說明
│   ├── notebook_executed.html                                     程式碼無關的 HTML 報告（11 MB）
│   │
│   ├── stage2/                                                    Wang 對照（2 檔）
│   │   ├── stage2_wang_merge_2024.csv                                 left-merge 後 2024 子集
│   │   └── stage2_wang_merge_comparison.csv                           逐欄 equality rate + Pearson r
│   │
│   ├── stage3/                                                    描述統計（6 檔）
│   │   ├── stage3_describe_overall.csv                                整體 describe（29 features）
│   │   ├── stage3_per_season_focus.csv                                FOCUS_FEATURES 2023 vs 2024 對照
│   │   ├── stage3_base_rates.csv                                      4 個二元 features 基準率
│   │   ├── stage3_corr_vs_win.csv                                     Pearson r + Spearman ρ vs win
│   │   ├── stage3_corr_vs_run_diff.csv                                Pearson r + Spearman ρ vs run_diff
│   │   └── stage3_skew_kurtosis_missing.csv                           偏態 / 峰度 / 缺失率診斷
│   │
│   ├── stage4/                                                    EDA 視覺化（10 張 PNG）
│   │   ├── stage4_small_multiples_top10.png                           histogram + KDE 2x5 grid
│   │   ├── stage4_spearman_heatmap.png                                Spearman 相關下三角熱圖
│   │   ├── stage4_pairplot_top5.png                                   top-5 features pairplot
│   │   ├── stage4_home_away_means.png                                 主客場 grouped bar
│   │   ├── stage4_monthly_trajectory.png                              每月趨勢線
│   │   ├── stage4_ecdf_top10.png                                      ECDF panels
│   │   ├── stage4_calendar_heatmap.png                                球場 × 週次熱圖
│   │   ├── stage4_win_rate_by_team.png                                球隊勝率排序 bar
│   │   ├── stage4_hexbin_H_run_diff.png                               H vs run_diff hexbin
│   │   └── stage4_violin_per_team.png                                 per-team top-3 features violin
│   │
│   ├── stage5/                                                    非監督特徵發現（33 檔）
│   │   ├── ── 5.1-5.2 篩選與標準化 ──
│   │   │   ├── stage5_filter_prune_log.csv                            filter prune 過程記錄
│   │   │   └── stage5_scaled_describe.csv                             標準化後 describe
│   │   ├── ── 5.3-5.6 PCA ──
│   │   │   ├── stage5_pca_scree.png                                   scree + 累積 PVE 圖
│   │   │   ├── stage5_pca_biplot.png                                  PC1-PC2 biplot + 箭頭
│   │   │   ├── stage5_pca_loadings_abs.csv                            |loadings| 矩陣（55 × 24）
│   │   │   ├── stage5_loadings_heatmap.png                            |loadings| 熱圖
│   │   │   └── stage5_pca_3d.html                                     plotly 3D 互動圖
│   │   ├── ── 5.7 K 共識（六方法投票）──
│   │   │   ├── stage5_kmeans_metrics.csv                              inertia / silhouette / CH / DBI × k
│   │   │   ├── stage5_gap_statistic.csv                               gap 統計 × k
│   │   │   ├── stage5_gmm_metrics.csv                                 BIC / AIC × k
│   │   │   ├── stage5_k_consensus_votes.csv                           六方法各自的最佳 k
│   │   │   └── stage5_k_consensus_panel.png                           2x3 metric 曲線 panel
│   │   ├── ── 5.8 階層分群最佳化（4 linkage + balance gate）──
│   │   │   ├── stage5_hierarchy_linkage_comparison.csv                每 linkage 的 cophenetic + 平衡後 k/sil
│   │   │   ├── stage5_hierarchy_full_matrix.csv                       每個 (linkage, k) 的 silhouette + 最小群比
│   │   │   ├── stage5_hierarchy_silhouette_sweep.csv                  (legacy) silhouette sweep
│   │   │   ├── stage5_dendrogram_4linkages.png                        4 linkage dendrogram 2x2
│   │   │   └── stage5_hierarchy_kselection.png                        silhouette + balance 雙圖
│   │   ├── ── 5.10 HDBSCAN ──
│   │   │   └── stage5_hdbscan_tree.png                                condensed tree 視覺化
│   │   ├── ── 5.9 GMM ──
│   │   │   └── stage5_gmm_bic.png                                     BIC / AIC × k 折線
│   │   ├── ── 5.11-5.12 validity + silhouette diag ──
│   │   │   ├── stage5_validity_panel.csv                              kmeans / hierarchy[ward] / gmm 三方比較
│   │   │   └── stage5_silhouette_per_point.png                        per-point silhouette bar
│   │   ├── ── 5.13-5.14 降維 sanity ──
│   │   │   ├── stage5_umap_pair.png                                   UMAP × (cluster, season) 雙面板
│   │   │   └── stage5_tsne_perplexity.png                             t-SNE perplexity 15/50 對比
│   │   ├── ── 5.15-5.18a 群解讀 ──
│   │   │   ├── stage5_cluster_means.csv                               每個 cluster × 所有 features 的平均
│   │   │   ├── stage5_cluster_stds.csv                                每個 cluster × 所有 features 的標準差
│   │   │   ├── stage5_cluster_radar.png                               FOCUS_FEATURES z-score radar
│   │   │   ├── stage5_cluster_boxplots.png                            notched + bootstrap CI boxplots
│   │   │   ├── stage5_shap_per_cluster.csv                            surrogate Tree-SHAP 排名
│   │   │   ├── stage5_meaningful_features.csv                         ANOVA F + MI + z-score 共識排名
│   │   │   └── stage5_anova_top12.png                                 top-12 ANOVA F bar chart
│   │   └── ── 5.19 跨季比較 ──
│   │       ├── stage5_season_cluster_xtab.csv                         (season × cluster) cross-tab
│   │       ├── stage5_cluster_freq_shift.png                          2023 vs 2024 grouped bar
│   │       └── stage5_season_cluster_sankey.html                      plotly Sankey 流向圖
│   │
│   └── stage6/                                                    綜合整理（4 檔）
│       ├── stage6_focus_overlap.csv                                   focus / lag features × (PCA loading + SHAP) overlap
│       ├── stage6_new_candidate_features.csv                          unsupervised 新增的 8 個候選 features
│       ├── stage6_feature_strategy.csv                                feature strategy 設計
│       └── stage6_research_design_summary.csv                         一頁研究設計摘要
│
└── docs/
    ├── plan.md                                                    研究計畫書
    └── knowledge_base/                                            從 course-material 蒸餾出的 KB
        ├── README.md                                                  KB index + schema 說明
        ├── Application_of_Machine_Learning_Models_for_Basebal.md      Lo et al. 2025 paper 摘要
        ├── topic03_measurement_1.md                                   評估指標（part 1）
        ├── topic03_measurement_3.md                                   評估指標（Practical-DS-with-R 角度）
        ├── topic05-1_PCA-SVD.md                                       PCA / SVD
        ├── topic05-2_featureExplain.md                                LIME / SHAP / PDP
        ├── topic05_featureReduction.md                                特徵選擇 + 抽取
        ├── topic06_visualization.md                                   視覺化型錄
        ├── topic07_data.md                                            資料處理
        ├── topic08_unsupervised.md                                    非監督學習（核心）
        └── topic09_supervised1_mem.md                                 kNN / Naive Bayes / 距離度量
```

## 主要結論（status quo）

| 指標 | 結果 |
|---|---|
| 樣本數 | 1320 team-game rows（2023 + 2024，去重後） |
| Pre-game features | 60+ 個 `prior_*` / `opp_prior_*` / `season_to_date_*` / `h2h_*` / `stadium_prior_*` |
| Pre-game ready | 1308/1320（99.1%）；前 1-4 場 NaN 由 imputer 補中位數 |
| Wang R port 對照 | 35/44 數值欄位 Pearson r ≥ 0.999（移植在數值上等價） |
| PCA k* @ 90% PVE | 24 PCs |
| K 共識（6 方法投票）| k=2 與 k=3 各得 2 票；採最小 k=2 |
| 階層分群最佳 linkage | `ward` k=2（cophenetic 0.327；balance gate 過 24.2%）。注意 average 雖 cophenetic 最高（0.647）但 k=2 退化成 1315 vs 5，被 balance gate 過濾 |
| **最終演算法** | **`kmeans` k=2**（silhouette 0.115、bootstrap-Jaccard 0.918） |
| Cluster 解讀 | cluster 0 = 近 5-10 場 run_diff↑（球隊熱）；cluster 1 = 近期 run_diff↓（球隊冷） |
| 新增候選 features | 8 個：`cluster_id` + `gmm_p0..p3` + `pc1..pc3` |

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
            │ 5.8       階層分群（4 linkage + balance gate）
            │ 5.9-5.11  GMM / HDBSCAN / validity + Jaccard
            │ 5.12-5.14 silhouette diag / UMAP / t-SNE
            │ 5.15-5.18 cluster mean / radar / notched box / SHAP
            │ 5.18a     ANOVA F + MI 重要性
            │ 5.19-5.20 跨季 shift + derived feature register
            ▼
Stage 6  synthesis（overlap、new candidates、design summary）
            ▼
Stage 7  export（DOWNLOAD_ALL flag 控制是否寫出 Results/stage*/）
```

## 快速開始

### 1. 直接讀

打開 [`Results/notebook_executed.html`](Results/notebook_executed.html) 即可——
所有 7 個 stage 的渲染輸出 + 中文解讀都已 inline，不需 Jupyter。

### 2. 在 Jupyter 重跑

```bash
./master.sh
```

`master.sh` 會：
1. 用 `jupyter nbconvert --execute` 跑完整本 notebook
2. 重新匯出 `Results/notebook_executed.html`

第一次跑會從 rebas.tw 下載 2024 release zip 到 `Data/2024/`（2023 已內附）。

### 3. 從零重建 notebook 或重生 Results/stage*/

詳見 [`Scripts/build/README.md`](Scripts/build/README.md)。

## 版本控制慣例

- **進 git**：`README.md` / `master.sh` / `.gitignore` / `Scripts/` / `Results/` / `docs/` / `Data/2023/`
- **不進 git**：`Derived/` 與 `Data/2024/CPBL-*` 內的執行時下載檔（由 `master.sh` 重新產出）
- 大型外部資料（如原本 199 MB 的 `course-material/` HTML 原檔）建議遷往 GitHub Release asset，不要進主 repo

## 主要參考

- [rebas.tw 開放資料](https://github.com/rebas-tw/rebas.tw-open-data) — 比賽原始 JSON（ODC-By 授權）
- [analyze_wang branch](https://github.com/cde52470/data_science/tree/analyze_wang) — 學長前期 supervised 預測程式 + cleaned CSV
- 課程 `course-material/`（199 MB HTML 原檔，已移出 repo；蒸餾版見 `docs/knowledge_base/`）
- Lo, T.-Y. et al. (2025). "Application of Machine Learning Models for Baseball Outcome Prediction." *Applied Sciences*.
