# Results/

最終產出。包含：

| 檔案 | 來源 | 用途 |
|---|---|---|
| `notebook_executed.html` | `jupyter nbconvert --to html` of `Scripts/cpbl_unsupervised_feature_discovery.ipynb` | 不開 Jupyter 也能看到所有 inline 輸出（圖、表、結果解讀） |

## 想匯出單獨檔案？

把 `Scripts/cpbl_unsupervised_feature_discovery.ipynb` 內的：

```python
DOWNLOAD_ALL = False
```

改成 `True` 並重跑 **Stage 7.3**，會在 `/tmp/cpbl_artifacts/` 寫出：

- `Results/figures/stage{N}_*.png` 與 `*.html`（plotly 3D / Sankey）
- `Results/tables/*.csv`

並打包成 `/tmp/cpbl_artifacts.zip`，notebook 末尾顯示一鍵下載連結。

預設不寫出這些檔案，是為了避免每次跑 notebook 都弄髒工作目錄。`Results/figures/`
與 `Results/tables/` 已加入 `.gitignore`——如果你想 commit 某個特定圖表，可以
手動 `git add -f Results/figures/the_one.png`。
