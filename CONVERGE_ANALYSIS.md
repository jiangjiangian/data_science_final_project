# CPBL 2024 主客場勝負分析（converge_analysis）

> 本文件為 `converge_analysis.ipynb` 的**結論摘要與方法說明**。完整的「可執行 notebook（含程式、圖、逐 cell 兩段【解釋】）＋ Results/ 全部產物」因檔案過大/含二進位圖，無法經 API 推送，請見最下方「取得完整內容」以 bundle 一鍵還原。

## 研究問題
以**團隊-單場**資料（一列＝一支球隊在一場比賽的表現）檢視中華職棒 2024 年主客場差異，回答：**單看「得分多寡」是否足以解釋主客勝負？若不夠，還缺了什麼？**

## 資料與方法

- **資料**：`cpbl_games_cleaned.csv`（`data` 分支，乾淨原始、每場一列、含逐局得分）。notebook 以 **`git fetch origin data`** 取檔，可獨立完整重現；所有節奏/情勢特徵皆由逐局得分**自行衍生**，不使用任何由比賽結果反推的標籤（避免結果/時間特性汙染）。
  - 限制：`H/BB/SO` 為**整場兩隊合計**、無法分主客，故不做每隊投打控制分析。
- **分析單位**：以 **team-game** 為主，並把「球隊」當分組因子（每隊分層 ＋ 解釋模型加 `C(team)` 固定效果），避免把六隊混為單一 population（Simpson's paradox）；`home_win`/勝差用 game-level。
- **科學流程（先探索、後立論）**：`EDA → 描述統計 → 推論統計 → 建模 → 結論`；假設只在 EDA 之後生成、結論只在最後出現。
- **方法嚴謹度**：cluster-robust 標準誤（依 `game_id` 分群，修正同場兩列非獨立）、GroupKFold（依 `game_id`）交叉驗證、permutation importance（取代有偏的 impurity）、連續勝差不分箱檢定＋分箱敏感度、效果量＋bootstrap 95% CI、Holm/BH 多重比較校正、Pythagorean 期望對照。
- **兩個分析開關 (gates)**：`USE_TIME_LAG`（預設 `True`，階段 4b 的預設預測特徵＝賽前 leak-free 滯後特徵）、`EXPORT_OUTPUTS`（預設 `False`，True 時把表/圖輸出到 `Results/`）。

## 由 EDA 浮現的待檢驗假設

| 假設 | 內容 |
|---|---|
| H1 情勢結構 | 情勢（險勝/常態/大比分）與主客勝負不獨立 |
| H2 勝差大小 | 主場勝的勝差小於客場勝 |
| H3 得分量不足 | 整場合計得分/安打量與勝負近乎無關 |
| H4 節奏情勢 | 先馳得點、領先過半場、逆轉等與勝負相關 |
| H5 球隊異質性 | 主場優勢因隊而異，須以球隊分組理解 |

## 主要結果

**現象（穩健）**：主場勝率 **52.8%** > 客場 **47.2%**，但主場平均得分 **4.16 < 客場 4.24**（淨分差 −0.087）——勝率與得分量反向。主場 **Pythagorean 殘差 +0.037**（實際 0.528 > 期望 0.491），客場 −0.037 → 主隊把相同得失分**更有效率地轉成勝場**。

| 假設 | 檢定 / 模型 | 結果 | 判定 |
|---|---|---|---|
| H1 | 情勢×勝負 卡方 | p=0.194, Cramér's V=0.096 | 分箱不顯著 |
| H1（不分箱）| `home_win ~ |分差|` 邏輯迴歸 | 係數 −0.078, **p=0.046**, OR=0.925 | 方向成立、效果弱（優勢集中近身戰）|
| H2 | 勝差 Mann-Whitney U | 主3.43 vs 客4.02, p=0.054, rbc=0.116, CI含0 | 邊緣、未達顯著 |
| H3 | 整場合計量 vs 主場勝 Spearman | 全部 |ρ|≤0.11 | 成立（量不指示勝負）|
| H4 | 先馳得點×勝負 卡方 | **p≈0（校正後仍顯著）**，先馳得點者約 70% 獲勝 | 穩健 |
| H5 | 每隊主場優勢 | **−0.067(中信) ~ +0.158(台鋼)**；6 隊 Wilcoxon p=0.156（n=6 檢力低）| 描述明確、推論受限 |

**多重比較校正（Holm/BH）**：整個檢定家族中，僅 **H4 先馳得點** 穩健顯著；H1、H2 不顯著。

### 解釋性模型（4a，cluster-robust，含球隊固定效果）

控制得分量與節奏後，**主場身分 `is_home` 顯著**：OR≈**1.96**（cluster-robust p=0.032）；**加入球隊固定效果 `C(team)` 後幾乎不變**（OR≈**2.02**, p=0.030）→ 主場效應是**隊內**真實效應、非球隊強弱混淆（正面回應 H5）。最強項為 `led_after_6`、`late_share`、`scored_first`。GroupKFold AUC：只用得分量 0.852 → 加主場+節奏 0.941；惟 `is_home` 的 permutation importance 僅 0.004 → **關聯顯著 ≠ 預測增益大**。

### 預測性模型（4b，time-lag gate True 與 False 都計算）

| 設定 | 特徵 | GroupKFold 樣本外 AUC | 性質 |
|---|---|---|---|
| **time-lag=True（預設, leak-free）** | 賽前滯後：先前勝率/淨分差/近10場得失分/休息天數/對手先前勝率/Elo | **0.492 ≈ 隨機** | 誠實的賽前預測基準 |
| **time-lag=False（對照）** | 同場：led_after_6/late_share/runs… | **0.941** | **資料洩漏**（賽前取不到），不能用於真實預測 |

→ 0.94 看似精準實為洩漏；這正說明 time-lag gate 為何**預設 True**：擋掉洩漏特徵、只留賽前資訊。

## 結論（平衡）

2024 CPBL 主場優勢**真實但溫和**，來源**不是得分變多**，而是「近身戰佔優 ＋ 把得分更有效率地轉換為勝場（Pythagorean 正殘差）＋ 節奏/情勢（先馳得點、晚段領先）」的綜合效果；控制球隊與得分後主場身分仍有顯著淨關聯（OR≈2）且為隊內效應。然而**賽前可預測性極低**（leak-free AUC≈0.49）——主場優勢可『解釋』卻難以『預測』。

**侷限與後續**：(1) `H/BB/SO` 為整場合計，無法做每隊投打控制；(2) 單季 358 場，H2/H5 檢力不足；(3) `led_after_6`/`late_share` 等同場特徵僅能用於解釋（會洩漏），不可用於賽前預測。**後續**：跨季擴充樣本、取得每隊投打與先發/傷兵資料、以 leverage/WPA 量化情勢，並以 time-lag 滯後特徵為起點建立真正的賽前預測模型（目標：穩定超越 AUC 0.5）。

## Results/ 產物結構（由 notebook 在 `EXPORT_OUTPUTS=True` 時產生）

```text
Results/
├── stage1_eda/            5 PNG（主客勝率/得分、各隊主場優勢、勝差分布、相關熱圖）
├── stage2_descriptive/    6 CSV（describe、主客比較、每隊主場優勢、每勝得分效率、Pythagorean）
├── stage3_inferential/    3 CSV（情勢卡方、每隊主場優勢、多重比較校正）
└── stage4_model/          5 CSV + 1 PNG（解釋模型、GroupKFold AUC、4b 兩設定係數與 AUC 對照、permutation importance）
```

## 取得完整內容（可執行 notebook + 全部 Results 圖表 + 資料）

完整內容已打包成 git bundle（由助理交付）。在本機還原並推上本分支：

```bash
# 1) 從 bundle 取出分支（含完整 notebook、Results/、資料與提交歷史）
git clone converge_analysis.bundle converge_full && cd converge_full
# 2) 指向本 repo 並推上本分支
git remote add final https://github.com/jiangjiangian/data_science_final_project.git
git push final converge-analysis:claude/feature-engineering-analysis-OkMa1
```

或在已有的本 repo clone 內，直接執行 notebook 重生全部圖表：

```bash
CONVERGE_EXPORT=true jupyter nbconvert --to notebook --execute --inplace converge_analysis.ipynb
```
