# CPBL 主客場勝率預測 — 期末報告（骨架）

> **狀態：SCAFFOLD。** 每節已給：①目的 ②核心論點句（可直接當段落首句）
> ③要插入的確切圖／表／數字＋來源檔 ④內容要點。把要點展開成散文即成稿。
> 數字全部來自已定案、已推上遠端的 artifacts —— **不要重算、不要改數字**，
> 對不上就是哪裡 stale，回頭查 `reports/progress.md`。
>
> 詳細技術細節已在 `Results/01_define_the_goal.md`（目標）、
> `reports/02a_cde52470_data_audit.md`（資料）、`reports/03_step1_to_step3.md`
> （pipeline＋Run A–E）。本檔是把它們串成一篇對外的學術敘事。
>
> **一句話定調（全文的脊椎）：** 這個專案的貢獻不是高 AUC，而是一套
> *時序嚴謹的評估方法論*，它**兩次**偵測並戳破了誘人的小樣本 holdout
> 假訊號 —— 誠實的負面結果，正是可發表的成果。

---

## 摘要 / Abstract

- **目的**：把 m1–m7 消融＋演算法比較整合成一句話 —— 「在兩季 CPBL
  資料上，賽前資訊能否預測主隊獲勝？」
- **核心論點句**：「我們建立了時序感知的 walk-forward 評估管線；它顯示
  *沒有任何特徵組（球場、天氣、球隊戰力、打者狀態、投手）能在樣本外
  區分於純主場優勢*，並兩次自動戳破 N=47 holdout 上的假訊號。」
- 必含數字：season-OOF AUC ≈ .50–.53；對照錨點 = Vegas 賠率 MLB 僅
  ≈ 58.2%。一句「負面結果與運動預測文獻一致，且方法論本身是貢獻」。
- 插入：**圖 `Results/figures/ablation_holdout_vs_oof.png`**（全文最關鍵
  一張，摘要可放縮圖或在此點名「見圖 1」）。

## 1. 問題定義 Problem Definition

- **目的**：交代 business question、target、分析單位、預先登記的成功門檻。
- **核心論點句**：「本研究預測一場*尚未開打*的 CPBL 例行賽主隊獲勝機率
  `P(is_home_win=1)`，並以預先登記的門檻檢驗各特徵組是否有賽前訊號。」
- 內容要點（全部出自 `Results/01_define_the_goal.md`，照抄勿改）：
  - target `is_home_win ∈ {0,1}`，平手剔除；單位 = 一場比賽。
  - 利害關係人／用途（§2 of charter）：運彩分析師需**校準機率**。
  - **預先登記的成功門檻**（charter §7，這段是科學誠信的關鍵）：
    - (a) 必勝：Test AUC 顯著高於 m1 截距 95% bootstrap CI 上界
    - (b) 可發表：Test AUC ≥ 0.60
    - (c) 可部署：Test AUC ≥ 0.62 且校準
  - 預先登記的假設：HS（球場有訊號）、HW（天氣有訊號），檢定法 LRT＋
    DeLong ΔAUC＋paired bootstrap。
- **重要敘事鉤子**：明說「我們*先*訂門檻*再*看結果」——後面 §6 誠實對照
  「三個門檻全未達」，這正是預先登記式分析的價值，不是失敗。

## 2. 資料 Data

- **目的**：來源、規模、不可用 Kaggle 的限制、資料工程踩到的真坑。
- **核心論點句**：「資料全部來自公開的野球革命 rebas JSON（無金鑰）與
  Open-Meteo（無金鑰），嚴格禁用 Kaggle／預打包資料集。」
- 內容要點：
  - rebas v0.1.0-2024 ＋ v0.1.0-2023.0/.1（**無 2022 release**）。
  - **資料工程實坑（值得寫進報告，展現嚴謹）**：2024 是 ASCII 檔名、
    2023 是中文檔名（`中職2023年-OpenData.json` 等 4 種）；原本寫死的
    `CPBL-*` glob **靜默吃掉整個 2023**、且不報錯。修正後 N 366→**678**。
    教訓：靜默資料遺漏比崩潰更危險 → 催生 `run_all.py` 的指紋護欄。
  - 天氣：CODiS 失敗（CAPTCHA）→ 改 Open-Meteo Archive；後證實天氣是
    最弱組（見 §5），但流程仍保留以完成 HW 假設檢定。
  - 細節引 `reports/02a_cde52470_data_audit.md`。
- 插入：N 與切分表（train 406 / valid 97 / test 47 / post-warmup 550；
  總場 678）—— 來源 `Results/eval/feature_schema.json:n`。

## 3. 方法論 Methodology  ★本報告的核心貢獻★

- **目的**：這是拿分的章節。把「為什麼我們的評估方式可信」講透。
- **核心論點句**：「單季 N 與 N=47 holdout 在統計上太吵，足以製造假
  訊號；因此我們以*時序感知 walk-forward OOF＋CV-AUC 選贏家＋bootstrap
  CI＋單一校準＋雙閾值*為評估骨幹，刻意不在 holdout 上選模型。」
- 內容要點（引 `reports/03_step1_to_step3.md` §3.1–3.4）：
  - 時序切分（**絕不隨機**）：train < 2024-08-01（2023 全進 train）／
    valid → 09-15／test ≥ 09-16。
  - walk-forward OOF（`ts_oof_proba`：`cross_val_predict` 不支援
    TimeSeriesSplit，自行 clone+fit 過去、預測未來）。
  - **per-group season-OOF**：對 m1–m7 各組做 leak-free walk-forward
    （455 場），這是判定訊號真偽的穩健指標。
  - 贏家由 **CV-AUC** 選，不用 N=47 holdout；每個 holdout AUC 附 95%
    bootstrap CI。單一 isotonic 校準（小 N 不堆疊）。雙閾值（0.5＋OOF-J）。
  - m1–m7 消融設計（演算法固定 logistic，特徵組變）：m1 截距／m2 球場
    ／m3 天氣／m4 球隊戰力／m5 打者狀態／**m6 投手**／m7 全部。
    說明 m6 自 charter 的「球場+天氣」改鎖為「投手」的理由（舊 m6
    實測 .467＝垃圾，槽位讓給 rebas 唯一未開採的槓桿）。

## 4. 特徵工程 Feature Engineering

- **目的**：列出每組特徵與其 leak-free 設計。
- **核心論點句**：「所有特徵嚴格只用比賽前可得資訊；滾動特徵只取該
  隊／該投手的*先前*場次。」
- 內容要點：
  - 球隊戰力：Elo（K=4, HFA+24, MoV）、Pythagenpat（30g, exp 1.83）、
    休息天數（cap 5）、Park Factor（時序 leave-one-out）。
  - 打者狀態：30 場滾動 OPS/HR/K%/BB%/runs diff＋該球場 OPS。
  - **投手（m6，本季新增）**：從 rebas `pitcherBox`（先發＝order==1，
    0/1356 例外驗證過）。先發近 5 場自身滾動 ERA/WHIP/K%/BB%/HR9
    ＋全隊投手 30 場滾動；冷啟動 <3 場 → 中位數補（聯盟回退）。
    強調「不用爬蟲、不用 CWA：rebas 本來就有」。

## 5. 結果 Results  ★放那張圖★

- **目的**：Run A→E 的演進敘事，誠實呈現。
- **核心論點句**：「隨著資料修正與特徵增強，*穩健*指標始終貼著 0.50；
  每一次 holdout 上的亮點都被 season-OOF 機制證實為雜訊。」
- **必放圖 1**：`Results/figures/ablation_holdout_vs_oof.png`
  —— 每組 N=47 holdout AUC vs leak-free season-OOF。**這張圖就是論點**：
  m6 投手 holdout .69 高聳、OOF .46 沉到 .50 線下；所有藍柱貼 .50。
- **Run 演進表**（數字來源 `reports/03` §3.5 與 `_final_metrics.json`）：

  | Run | 設定 | 穩健指標 | 解讀 |
  |---|---|---|---|
  | A | N=366, pre-weather | RF holdout .656 | 後證實 N=47 抽樣噪音 |
  | B | N=366, +weather | season-OOF **.504** | 擲銅板；無組勝截距 |
  | C | N=678, 2023 修復 | season-OOF **.538** | 純加資料微升（真實但小）|
  | D | N=678, +投手 | holdout m6 **.689** | 誘人 → 但 N=47 |
  | E | per-group season-OOF | m6 **.463** | **.689 是噪音，第二次中陷阱** |

- **per-group season-OOF 表**（`_final_metrics.json:ablation_season_oof`）：
  m1≈.50 / m2 .512 / m3 .524 / m4 .500 / m5 .500 / **m6 .463** / m7 .495。
  455 場 OOF 的 CI≈±.05 → 全是 .50 附近一帶。
- **per-fold 證據**（`ablation_season_oof_folds.m6`）：
  `[.441,.501,.406,.432,.584]` → **高變異雜訊，非系統性符號翻轉**
  （m4 [.52,.47,.49,.53,.53]、m7 同樣亂跳）—— 完整刻畫了「就是雜訊」。
- 生產模型：rf/m7，CV-AUC .546，season-OOF .528，holdout .640
  CI[.451,.806]。**連 CI 一起報，絕不單報 .640。**
- 附 `model_comparison.png` / `calibration.png` / `shap_summary.png`
  作輔助，但主角是圖 1。

## 6. 對照預先登記門檻 ＋ 討論 Discussion

- **目的**：科學誠信的高潮 —— 拿 §1 的門檻逐一對帳。
- **核心論點句**：「三個預先登記門檻（a 顯著勝截距、b ≥.60、c ≥.62）
  *全部未達*；HS／HW 假設亦未獲支持 —— 這是資料誠實告訴我們的事實。」
- 內容要點：
  - (a) 未達：無組之 season-OOF 區分於 m1；m6 holdout 一度像達標(a)，
    但 season-OOF .463 推翻 —— **這正是 charter 預先指定 bootstrap/
    DeLong 的理由，方法論做到了它該做的事**。
  - (b)(c) 未達：穩健 AUC ≈ .50–.53 ≪ .60。
  - **為何這是預期、不是失敗**：運動單場預測本就接近隨機；引文獻錨點
    —— Vegas 賠率（職業運動最強賽前預測、含完整市場資訊）MLB 僅
    ≈58.2%；學術 ML 57–59.5%（A. Cui, Wharton 2020；Entropy 24(2):288）。
    兩季 CPBL ≈.50–.53 OOF 落在理論預期內。
  - **方法論教訓（報告賣點）**：Run A .656、Run D m6 .689 兩個假訊號
    都被同一套 season-OOF＋CI 機制戳破 → 小樣本 holdout 排名會說謊，
    圖 1 是活教材。
  - 限制：兩季 N、無 probable starter（賽前不可得 → 部署侷限）、
    CPBL 樣本量遠小於 MLB。

## 7. 結論 Conclusion

- **核心論點句**：「在現有公開資料與兩季規模下，CPBL 單場主隊勝負於
  賽前接近不可預測；本專案的可交付成果是*能正確揭露此事實的嚴謹
  方法論*，而非一個被噪音美化的預測數字。」
- 重申：不再加特徵／調參（＝擬合噪音）；生產模型誠實附 CI 呈現。

## 8. 部署 Deployment（R Shiny，後續 Sub-Agent 6）

- 預算 artifacts 已就緒：`predictions.csv` / `best_model.joblib` /
  `feature_schema.json` / 四張圖。Shiny 零計算、只渲染。
- **落地文案定調**：儀表板*不是*預測產品，是「方法論展示＋圖 1 陷阱
  ＋誠實 AUC≈.53 附 CI」。避免任何「準確預測」字眼。

## 9. 可重現性 Reproducibility

- 一鍵：`colab_run.ipynb`（Run all）→ `run_all.py`（step1→3）。
- 防呆：`run_all.py` 頂部 code-fingerprint＋硬斷言投手欄進輸出，
  stale 即 SystemExit（曾兩次被 stale Colab 製造混淆 → 根治）。
- 決策全程記於 `reports/progress.md`（newest-on-top）。

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
- [ ] 圖 1 放進摘要與 §5，加完整 caption（解釋橘 vs 藍、.50 線、m6 反差）。
- [ ] §1 的門檻數字、§5 的 Run 表逐一對 `Results/eval/_final_metrics.json`
      與 `reports/03` 校對（對不上＝stale，勿手改）。
- [ ] 決定輸出格式：純 Markdown 交件，或轉 PDF（pandoc）/ Rmd knit。
- [ ] charter 的舊 m1–m7（m6=球場+天氣）→ 在 §3 明說已鎖為 m6=投手，
      避免與 `Results/01_define_the_goal.md` 表面矛盾（附一句變更理由）。
