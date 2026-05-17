# CPBL 主客場勝率預測 — 期末報告（骨架）

> **狀態：SCAFFOLD。** 結構依資料科學生命週期五步驟（`.claude/agents/`
> 01–05）：**定義目標 → 獲取資料 → 探索資料 → 建立模型 → 評估模型**，
> 末接結論／部署／可重現性。每節給：①該步驟回答的問題 ②可直接當段落
> 首句的核心論點句 ③要插入的確切圖／表／數字＋來源檔 ④內容要點。
> 把要點展開成散文即成稿。
>
> **數字全部引用已定案、已推上遠端的 artifacts —— 不要重算、不要改。**
> 對不上＝哪裡 stale，回頭查 `reports/progress.md`。
>
> 詳細技術細節：`Results/01_define_the_goal.md`（charter）、
> `reports/02a_cde52470_data_audit.md`（資料審計）、
> `reports/03_step1_to_step3.md`（pipeline ＋ Run A–E 完整數據）。
>
> **全文脊椎（一句話）：** 本專案的貢獻不是高 AUC，而是一套*時序嚴謹
> 的評估方法論*，它**兩次**自動偵測並戳破了 N=47 holdout 上的假訊號
> —— 一個被正確揭露的誠實負面結果，就是可發表的成果。

---

## 摘要 Abstract

- **核心論點句**：「在兩季 CPBL 公開資料上，我們以時序感知 walk-forward
  評估證明：球場、天氣、球隊戰力、打者狀態、投手等特徵組*皆無法在樣本
  外區分於純主場優勢*，且方法論兩次自動戳破 holdout 假訊號。」
- 必含：season-OOF AUC ≈ .50–.53；錨點 Vegas 賠率 MLB 僅 ≈58.2%。
- 插入 **圖 1 `Results/figures/ablation_holdout_vs_oof.png`**（全文最關鍵
  一張，摘要點名「見圖 1」）。
- 一句方法論貢獻定調 + 一句「負面結果與運動預測文獻一致」。

---

## 步驟 1 — 定義目標 Define the Goal

> *"What problem am I solving?"* — 生命週期第一節；目標不利則下游全錯。

- **目的**：鎖定 business question、target、分析單位、**預先登記**的成功
  門檻與假設。
- **核心論點句**：「本研究預測一場*尚未開打*的 CPBL 例行賽主隊獲勝機率
  `P(is_home_win=1)`，並以*事前*訂定的門檻檢驗各特徵組是否帶賽前訊號。」
- 內容要點（全部出自 `Results/01_define_the_goal.md`，照抄勿改）：
  - target `is_home_win ∈ {0,1}`；平手剔除；單位 = 一場比賽。
  - 利害關係人（charter §2）：運彩分析師需**校準機率**（AUC 高但
    over-confident 會直接賠錢）→ 解釋為何後面堅持報 Brier／校準曲線。
  - **預先登記成功門檻**（charter §7 — 這段是科學誠信的關鍵）：
    (a) 必勝＝Test AUC 顯著高於 m1 截距 95% bootstrap CI 上界；
    (b) 可發表＝Test AUC ≥ 0.60；(c) 可部署＝Test AUC ≥ 0.62 且校準。
  - 預先登記假設 HS（球場）、HW（天氣），檢定法 LRT＋DeLong ΔAUC＋
    paired bootstrap。
- **方法論變更（誠實揭露，放這節結尾一段）**：charter 原規劃 R／
  tidymodels；因 Colab 上 tidymodels 過慢、且授課允許 Python，**全流程
  改以 Python 實作**，R 僅留參考鏡像。charter 的舊 m1–m7（m6＝球場+
  天氣）後因實測 m6≈.467＝垃圾，**m6 槽位改鎖為「投手」**（理由見步驟
  4）；概念生命週期不變，實作與 m6 定義有調整，於此聲明以免與 charter
  表面矛盾。

## 步驟 2 — 獲取資料 Acquire Data

> *"What information do I need?"* — 把 charter 轉成證據；raw data 視為
> 寫一次、永不竄改、可重現的 WORM 儲存。

- **目的**：來源、規模、合法性、provenance，以及資料工程踩到的真坑。
- **核心論點句**：「資料全部來自公開的野球革命 rebas JSON 與 Open-Meteo
  （皆無金鑰），嚴格禁用 Kaggle／預打包資料集；每次擷取可位元級重現。」
- 內容要點：
  - rebas v0.1.0-2024 ＋ v0.1.0-2023.0/.1（**無 2022 release**）；
    SHA256 provenance manifest（`data/raw/_provenance/`）。
  - **資料工程實坑（必寫，展現嚴謹）**：2024 為 ASCII 檔名、2023 為
    *中文*檔名（`中職2023年-OpenData.json` 等 4 種）；原本寫死的
    `CPBL-*` glob **靜默吃掉整個 2023 且不報錯** → N 卡在 366。修正
    `*OpenData*` 後 N 366→**678**。教訓：靜默資料遺漏比崩潰更危險。
  - 天氣：原規劃 CWA CODiS，遇 CAPTCHA／session 失敗 → 改 **Open-Meteo
    Archive**（ERA5，無金鑰，反正 ERA5 已吸收 CWA 測站）；硬失敗保護
    （缺座標／缺漏 >50% 直接 SystemExit，不靜默塞 NA）。
  - **不需爬蟲、不需 CWA 金鑰**：投手資料 rebas `pitcherBox` 本來就有。
  - 細節引 `reports/02a_cde52470_data_audit.md`。
- 插入：N/切分表（train 406 / valid 97 / test 47 / post-warmup 550；
  總場 678）—— 來源 `Results/eval/feature_schema.json:n`。

## 步驟 3 — 探索資料 Explore the Data

> *"Find patterns that lead to solutions."* — EDA 是最便宜的地方殺掉
> 壞假設、挖出資料品質地雷。

- **目的**：用 EDA 結果驅動特徵設計與資料品質決策。
- **核心論點句**：「探索性分析確認 Park Factor 的球場差異與缺漏結構、
  驗證 rebas `pitcherBox` schema，並以 PCA／K-means 檢視特徵空間 ——
  後兩者*獨立佐證*了賽前無訊號的負面結論。」
- 內容要點：
  - Park Factor：澄清湖 ≈1.18（打者球場）、天母 ≈0.86（投手球場）等
    （`data/processed/park_factors.csv`）。
  - 缺漏審計＋插補決策樹（引 `reports/02a`）；平手場剔除規則。
  - **投手 schema 驗證（notebook Cell 4 診斷）**：每場每邊*恰好一個*
    `order==1`（0/1356 例外）→ 先發識別可靠；欄位
    `IPOuts/NP/BF/H/HR/BB/IBB/HB/SO/R/ER`；每位先發中位數 ~10 場 →
    決定「近 5 場滾動 + <3 場冷啟動回退」。
  - 打者狀態 30 場滾動分布；天氣 × 得分初探（後證實天氣最弱）。
  - **PCA / K-means（notebook Cell 7b，純探索、不餵 m1–m7 模型）**：
    - 天氣 4 變數 PCA：scree + PC1–PC2 散點依勝負上色 → **主成分空間
      不分主隊勝負**（`eda_weather_pca.png`），與「天氣是最弱組
      （season-OOF .524≈噪音）」一致。
    - 以 `diff_*` 比賽輪廓 K-means（k=4，*文件化選擇、非調參*）：
      找得到打法分群，但**各群主場勝率 ≈ 持平於整體基準**
      （`eda_kmeans.png`）→ 結構存在於*打法*、不存在於*勝負*。
    - **定位明確**：非監督探索、**不進模型**；從另一角度*獨立印證*
      負面結論（不是用來提升 AUC）。
- 圖：`eda_weather_pca.png`、`eda_kmeans.png`、`shap_summary.png`
  （步驟 5）；Park Factor 表。

## 步驟 4 — 建立模型 Build the Model

> *"Build the model."* — 小樣本先行；m1–m7 漸進消融，演算法固定先變
> 特徵、再固定特徵變演算法。

- **目的**：特徵工程 + 消融設計 + 時序建模管線。
- **核心論點句**：「所有特徵嚴格只用賽前可得資訊；以 m1–m7 消融（演算法
  固定 logistic）量化每組特徵的邊際貢獻，贏家由 CV-AUC 選（絕不用 N=47
  holdout）。」
- 內容要點：
  - 特徵組（皆 leak-free，滾動只取*先前*場次）：
    - 球隊戰力：Elo(K=4,HFA+24,MoV)、Pythagenpat(30g,1.83)、休息(cap5)、
      Park Factor（時序 leave-one-out）。
    - 打者狀態：30 場滾動 OPS/HR/K%/BB%/runs diff＋該球場 OPS。
    - **投手（m6，本季新增、本專案關鍵嘗試）**：rebas `pitcherBox`
      → 先發(order==1)近 5 場自身滾動 ERA/WHIP/K%/BB%/HR9＋全隊投手
      30 場滾動；冷啟動 <3 場 → 中位數補（聯盟回退）；主客場合併
      （投球技術與場地無關）。**不需爬蟲、不需 CWA**。
  - m1–m7（演算法固定 logistic）：m1 截距／m2 球場／m3 天氣／m4 球隊
    戰力／m5 打者狀態／**m6 投手**／m7 全部（5 組）。說明舊 m6（球場+
    天氣，實測 .467 垃圾）退役、槽位讓給投手的理由。
  - 時序切分（**絕不隨機**）：train < 2024-08-01（2023 全進 train）／
    valid → 09-15／test ≥ 09-16；walk-forward OOF（`ts_oof_proba`：
    `cross_val_predict` 不支援 TimeSeriesSplit，自行 clone+fit）。
  - 演算法比較（特徵固定 m7）：logit／glmnet／RF／XGBoost／LightGBM，
    `TimeSeriesSplit(5)` GridSearch；單一 isotonic 校準（小 N 不堆疊）。
  - 實作 = **單一自含 notebook `python/cpbl_pipeline.ipynb`**（step1→1b
    →2→3 全內嵌；不 clone、不 subprocess）。

## 步驟 5 — 評估模型 Evaluate the Model  ★放圖 1★

> *"Does it actually solve my problem?"* — 別愛上單一指標；AUC 給排序、
> 校準給信任、CI 給不確定性。

- **目的**：以穩健指標評估，誠實對照預先登記門檻。
- **核心論點句**：「以 per-group season-OOF（leak-free walk-forward，455
  場）評估：*沒有任何特徵組可與主場優勢區分*；每一次 holdout 亮點都被
  season-OOF＋bootstrap CI 證實為雜訊。」
- **必放圖 1**：`Results/figures/ablation_holdout_vs_oof.png` —— 每組
  N=47 holdout AUC vs leak-free season-OOF。**這張圖就是論點**：m6 投手
  holdout .69 高聳、OOF .46 沉到 .50 線下；所有藍柱貼 .50。
- **Run 演進表**（來源 `reports/03` §3.5 ＋ `_final_metrics.json`）：

  | Run | 設定 | 穩健指標 | 解讀 |
  |---|---|---|---|
  | A | N=366, pre-weather | RF holdout .656 | 後證實 N=47 抽樣噪音 |
  | B | N=366, +weather | season-OOF **.504** | 擲銅板；無組勝截距 |
  | C | N=678, 2023 修復 | season-OOF **.538** | 純加資料微升（真實但小）|
  | D | N=678, +投手 | holdout m6 **.689** | 誘人 → 但 N=47 |
  | E | per-group season-OOF | m6 **.463** | **.689 是噪音，第二次中陷阱** |

- **per-group season-OOF**（`_final_metrics.json:ablation_season_oof`）：
  m1≈.50 / m2 .512 / m3 .524 / m4 .500 / m5 .500 / **m6 .463** / m7 .495
  （455 場 OOF 的 CI≈±.05 → 全是 .50 附近一帶）。
- **per-fold 證據**（`ablation_season_oof_folds.m6`）：
  `[.441,.501,.406,.432,.584]` → **高變異雜訊，非系統性符號翻轉**
  （m4/m7 同樣亂跳）—— 完整刻畫「就是雜訊、無一致方向」。
- 校準／雙閾值：isotonic 是否服務看 holdout Brier；閾值取 leak-free
  OOF Youden-J，holdout 同時報 0.5 與調整閾值（不靜默替換）。
  輔助圖 `calibration.png` / `model_comparison.png` / `shap_summary.png`。
- **對照預先登記門檻**：(a)(b)(c) **全部未達**；HS／HW 假設未獲支持。
  m6 holdout 一度像達標 (a)，但 season-OOF .463 推翻 —— **這正是
  charter 預先指定 bootstrap/DeLong 的理由，方法論做到了它該做的事**。

## 結論 Conclusion

- **核心論點句**：「在現有公開資料與兩季規模下，CPBL 單場主隊勝負於
  賽前接近不可預測；可交付成果是*能正確揭露此事實的嚴謹方法論*，而非
  被噪音美化的數字。」
- 為何是預期、非失敗：運動單場預測本就接近隨機；**Vegas 賠率（職業
  運動最強賽前預測、含完整市場資訊）MLB 僅 ≈58.2%**，學術 ML 57–59.5%
  （A. Cui, Wharton 2020；Entropy 24(2):288）。兩季 CPBL ≈.50–.53 OOF
  落在理論預期內。
- 方法論教訓：Run A .656、Run D m6 .689 兩個假訊號被同一套機制戳破 →
  小樣本 holdout 排名會說謊，圖 1 為活教材。
- 不再加特徵／調參（＝擬合噪音）；生產模型 rf/m7（season-OOF .528，
  holdout .640 CI[.45,.81]）誠實連 CI ＋負面消融一起呈現。
- 限制：兩季 N、無 probable starter（賽前不可得 → 部署侷限）、CPBL
  樣本量遠小於 MLB。

## 步驟 6（後續）— 部署 R Shiny

- 預算 artifacts 已就緒：`Results/eval/predictions.csv` /
  `models/best_model.joblib` / `Results/eval/feature_schema.json` /
  4 張圖。Shiny **零計算**、只渲染。
- **落地文案定調**：儀表板*不是*預測產品，是「方法論展示＋圖 1 陷阱
  ＋誠實 AUC≈.53 附 CI」。避免任何「準確預測」字眼。
- 由 Sub-Agent 6（`@shiny-deployer`）執行。

## 可重現性 Reproducibility

- **單一自含 notebook**：`python/cpbl_pipeline.ipynb` —— step1→step1b→
  step2→step3 全部內嵌為 cell，`Runtime → Run all` 一鍵跑完。不 clone
  repo、不跑 subprocess、無 `.py` 相依（球場 lookup 內嵌）；無 stale
  程式問題（notebook 本身即程式）。
- 決策全程記於 `reports/progress.md`（newest-on-top）。
- R 參考鏡像保留於 `R/`（非執行路徑）。

## 參考文獻 References

- A. Cui, *Forecasting Outcomes of MLB Games Using Machine Learning*,
  Wharton (2020).
  https://fisher.wharton.upenn.edu/wp-content/uploads/2020/09/Thesis_Andrew-Cui.pdf
- *Exploring and Selecting Features to Predict the Next Outcomes of MLB
  Games*, Entropy 24(2):288 (2022). https://www.mdpi.com/1099-4300/24/2/288
- 野球革命 rebas open data：https://github.com/rebas-tw/rebas.tw-open-data
- Open-Meteo Archive API：https://open-meteo.com/

---

### 給寫稿者的待辦（TODO）

- [ ] 每節「核心論點句」展開成 1–3 段散文（語氣：自信、誠實、不防衛）。
- [ ] 圖 1 放進摘要與步驟 5，加完整 caption（橘 vs 藍、.50 線、m6 反差）。
- [ ] 步驟 1 門檻、步驟 5 Run 表逐一對 `Results/eval/_final_metrics.json`
      與 `reports/03` 校對（對不上＝stale，勿手改）。
- [ ] 決定輸出格式：純 Markdown 交件 / pandoc → PDF / Rmd knit。
- [ ] 步驟 1 結尾的「R→Python＋m6 relock」聲明潤飾，確保與
      `Results/01_define_the_goal.md` 不矛盾。
