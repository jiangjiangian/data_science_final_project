# Results/

最終產出。除了 `notebook_executed.html` 之外，所有圖表與表格都已分 stage
拆成子資料夾，方便快速翻找與引用。

## 目錄結構

```
Results/
├── README.md                     ← 你在這裡
├── notebook_executed.html        ← 完整 notebook 的 HTML 匯出（11 MB）
├── stage2/                       ← 前處理階段的對照表
│   ├── stage2_wang_merge_2024.csv               學長 + 本 notebook 的 2024 對照 left-merge
│   └── stage2_wang_merge_comparison.csv         逐欄 equality_rate + Pearson r
├── stage3/                       ← 描述統計表
│   ├── stage3_describe_overall.csv              整體 describe
│   ├── stage3_per_season_focus.csv              focus features 的 2023 vs 2024 比較
│   ├── stage3_base_rates.csv                    二元 features 的基準率
│   ├── stage3_corr_vs_win.csv                   與 win 的 Pearson/Spearman 相關
│   ├── stage3_corr_vs_run_diff.csv              與 run_diff 的相關
│   └── stage3_skew_kurtosis_missing.csv         偏態/峰度/缺失率診斷
├── stage4/                       ← EDA 視覺化（10 張 PNG）
│   ├── stage4_small_multiples_top10.png         FOCUS_FEATURES histogram + KDE 2x5
│   ├── stage4_spearman_heatmap.png              Spearman 相關熱圖（下三角）
│   ├── stage4_pairplot_top5.png                 top-5 features pairplot
│   ├── stage4_home_away_means.png               主客場 mean 比較
│   ├── stage4_monthly_trajectory.png            每月趨勢
│   ├── stage4_ecdf_top10.png                    ECDF panels
│   ├── stage4_calendar_heatmap.png              球場 × 週次熱圖
│   ├── stage4_win_rate_by_team.png              球隊勝率排序
│   ├── stage4_hexbin_H_run_diff.png             H vs run_diff hexbin
│   └── stage4_violin_per_team.png               top-3 features per-team violin
├── stage5/                       ← 非監督學習產出（29 個檔案，PNG + CSV + plotly HTML）
│   ├── PCA 系列
│   │   ├── stage5_pca_scree.png
│   │   ├── stage5_pca_biplot.png
│   │   ├── stage5_pca_loadings_abs.csv
│   │   ├── stage5_loadings_heatmap.png
│   │   └── stage5_pca_3d.html                   plotly 3D 互動圖
│   ├── 分群算法
│   │   ├── stage5_k_consensus_votes.csv         六方法 K 共識投票
│   │   ├── stage5_k_consensus_panel.png         2x3 metric 曲線
│   │   ├── stage5_kmeans_metrics.csv
│   │   ├── stage5_gap_statistic.csv
│   │   ├── stage5_gmm_metrics.csv
│   │   ├── stage5_gmm_bic.png
│   │   ├── stage5_dendrogram.png                Ward
│   │   └── stage5_hdbscan_tree.png              HDBSCAN condensed tree
│   ├── 分群驗證
│   │   ├── stage5_validity_panel.csv            silhouette/CH/DBI/bootstrap-Jaccard
│   │   └── stage5_silhouette_per_point.png
│   ├── 降維視覺化
│   │   ├── stage5_umap_pair.png                 UMAP 按 cluster / season
│   │   └── stage5_tsne_perplexity.png           t-SNE perplexity sanity
│   ├── 群解讀
│   │   ├── stage5_cluster_means.csv
│   │   ├── stage5_cluster_stds.csv
│   │   ├── stage5_cluster_radar.png
│   │   ├── stage5_cluster_boxplots.png          notched + bootstrap CI
│   │   ├── stage5_shap_per_cluster.csv          surrogate Tree-SHAP 排名
│   │   ├── stage5_anova_top12.png               ANOVA F top-12
│   │   ├── stage5_meaningful_features.csv       ANOVA F + MI + z-score 共識排名
│   │   └── stage5_filter_prune_log.csv          5.1 prune log
│   └── 跨季比較
│       ├── stage5_season_cluster_xtab.csv       (season × cluster) cross-tab
│       ├── stage5_cluster_freq_shift.png        2023 vs 2024 grouped bar
│       └── stage5_season_cluster_sankey.html    plotly Sankey 流向圖
│   └── stage5_scaled_describe.csv               5.2 標準化後 describe
└── stage6/                       ← 綜合整理
    ├── stage6_focus_overlap.csv                 focus / lag features × PC loading × SHAP 共識
    ├── stage6_new_candidate_features.csv        非監督新增候選特徵
    ├── stage6_feature_strategy.csv              feature strategy 設計表
    └── stage6_research_design_summary.csv       一頁研究設計摘要
```

## 如何重新生成

```bash
./master.sh
```

`master.sh` 會：
1. 重跑 notebook（會自動下載缺失的 rebas 資料）
2. 重生 `notebook_executed.html`

要連帶把這份 `Results/stage*/` 一起重生，跑：

```bash
python3 Scripts/build/export_results.py
```

（如沒有該腳本，可參考 `Scripts/build/README.md` 描述的 pipeline 手動執行。）

## 設計選擇

- 每張圖、每張表的檔名都用 `stage{N}_<snake_case>.<ext>` 命名，方便視覺掃描歸屬。
- Plotly 圖（3D PCA、Sankey）保存為互動式 `.html`；matplotlib 圖為 `.png`。
- CSV 用 UTF-8 with BOM 編碼（`utf-8-sig`），確保 Excel 開啟時不會中文亂碼。
