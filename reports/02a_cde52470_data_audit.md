# 02a — cde52470:data 乾淨資料審計 + 打者狀態定義

> **Sub-Agent 2 (data-collector) handoff**
> Source: `https://github.com/cde52470/data_science/tree/data`
> Mirror path (sandbox, gitignored): `data/raw/cde52470_mirror/`
> Auditor script: `scripts/eda_cde52470_audit.py`
> Date: 2026-05-14

---

## 0. TL;DR

| 項目 | 結論 |
|---|---|
| **可用 baseline 標的** | ✅ 360 場 (CPBL 2024 整季)，`home_win` 完整無 NA |
| **時間切分可行性** | ✅ 2024-03-30 → 2024-10-11，可做 walk-forward CV |
| **stadium 名稱** | ⚠️ 11 個 (charter 只列 7 個) — 需要 normalize map |
| **team 名稱** | ✅ 6 隊，主/客各 60 場完全平衡 |
| **H, HR, 2B, 3B, BB, SO** | 🔴 **是主+客合計**，對 home_win 預測幾乎無用 (corr <0.11) |
| **天氣特徵** | 🔴 **完全缺失** — 必須另外抓 CWA，否則 m3/m5/m6/m7 全廢 |
| **打者狀態原料** | 🟢 raw JSON 的 `homeBatterBox`/`awayBatterBox` 含 24 個 per-player 欄位，可重建 |
| **資料量是否夠** | ⚠️ 360 場單季偏小，可做 POC 但 production 建議補 2022-2023 |

---

## 1. Schema 對照 (charter §5/§10 vs 來源)

| charter 欄位 | 來源欄位 | 狀態 |
|---|---|---|
| `game_id` | ❌ 無 | 需 derive：`YYYYMMDD-HHMM-{stadium}-{awayTeam}-{homeTeam}` |
| `date` | `date` (str datetime) | ✅ 解析後 OK |
| `stadium` | `stadium` (full Chinese name) | ⚠️ 11 種，需 normalize 對應 charter §10 的 7 個短名 |
| `home_team` | `homeTeam` | ✅ rename |
| `away_team` | `awayTeam` | ✅ rename |
| `home_score` | `home_total_score` | ✅ rename |
| `away_score` | `away_total_score` | ✅ rename |
| `inning_scores` | `homeScores`/`awayScores` (str list) | ✅ `ast.literal_eval()` |
| `is_home_win` | `home_win` | ✅ rename |
| `temperature` | ❌ 無 | 🔴 **必抓 CWA** |
| `humidity` | ❌ 無 | 🔴 **必抓 CWA** |
| `wind_speed` | ❌ 無 | 🔴 **必抓 CWA** |
| `wind_dir` | ❌ 無 | 🔴 **必抓 CWA** |

---

## 2. EDA 核心發現

### 2.1 Target balance — 主場優勢確認
```
home_win = 1 : 189 場 (52.5%)
home_win = 0 : 171 場 (47.5%)
ties (扣除前): 2 場
```
主場勝率 52.5%，符合 MLB / NPB 文獻範圍 (53-55%)。
**baseline m1 (intercept-only) 預期 accuracy ≈ 0.525**。

### 2.2 Stadium 分佈 — 真實 roster 比 charter 多 4 個小球場

| Stadium | N | home_win_rate | 註記 |
|---|---:|---:|---|
| 新北市立新莊棒球場 | 54 | **42.6%** | ⚠️ 富邦主場，主場優勢反而負 |
| 樂天桃園棒球場 | 53 | 56.6% | 樂天主場，桃猿主場優勢明顯 |
| 臺南市立棒球場 | 51 | 62.7% | 統一獅主場，最強主場優勢 |
| 臺中市洲際棒球場 | 48 | 52.1% | 中信兄弟主場 |
| 臺北市立天母棒球場 | 47 | 51.1% | 味全龍主場 |
| 澄清湖棒球場 | 40 | 50.0% | 台鋼雄鷹主場 |
| 臺北大巨蛋 | 38 | 55.3% | indoor，6 隊輪流主場 |
| 花蓮縣立德興棒球場 | 10 | 70.0% | N 小，慎用 |
| 嘉義市立棒球場 | 8 | 50.0% | N 小 |
| 臺東棒球村第一棒球場 | 7 | 42.9% | N 小 |
| 斗六棒球場 | 4 | 0.0% | N 小，極端值 |

**Charter §10 的 7 球場 vs 來源 11 球場差異**：
- charter 寫的 `嘉義` (Lamigo old) 對應 `嘉義市立棒球場` ✅
- charter 未列：天母、花蓮、臺東、斗六 — 都是「下鄉 / 客場主辦」場次

→ Sub-Agent 3 (EDA) 要更新 stadium normalization map，並考慮把 N<10 的小球場標 `is_minor_venue = TRUE` 以便 m2/m4/m6 分組或合併處理。

### 2.3 Team↔Stadium 主場對應 (建議寫進 normalization)

| 球隊 | 主場 (>40 場) | 次要主場 |
|---|---|---|
| 中信兄弟 | 臺中市洲際 (48) | 大巨蛋 (10), 臺東 (2) |
| 台鋼雄鷹 | 澄清湖 (40) | 嘉義 (6), 大巨蛋 (5), 臺東 (5), 花蓮 (2), 斗六 (2) |
| 味全龍 | 臺北市立天母 (45) | 大巨蛋 (10), 花蓮 (3), 斗六 (2) |
| 富邦悍將 | 新北市立新莊 (54) | 大巨蛋 (6) |
| 樂天桃猿 | 樂天桃園 (53) | 大巨蛋 (3), 臺南 (2), 天母 (2) |
| 統一7-ELEVEn獅 | 臺南市立 (49) | 花蓮 (5), 大巨蛋 (4), 嘉義 (2) |

### 2.4 得分分佈 — 主隊「平均得分較低」但勝率仍高
```
home_total_score: mean 4.14, std 2.97, max 16
away_total_score: mean 4.23, std 3.32, max 17  ← 客隊 average 反而高
total_score:      mean 8.38, max 23
```
看似矛盾但合理：**主隊領先時九下不擊**會壓低主隊得分，但仍贏球。**這是 home-field 第二個訊號**（除了勝率），可當 feature 使用：`home_offensive_efficiency = home_total_score / home_innings_played`。

### 2.5 Innings 與延長賽
- 平均 9.08 局，延長賽 (≥10 局) 26 場 = **7.2%**
- 提前結束 (walk-off, away_innings > home_innings) 僅 1 場 → 9 下半「主場領先 → 不再打」應該還有更多，可能是 cleaner 抓資料時主場最後一局已記錄為 0 或 X。後續看 raw JSON 的 inning 字串內容需更仔細處理 (`X` 代表「未上場」)。

### 2.6 H/HR/2B/3B/BB/SO 是 **主+客合計**，無預測力
clean_games.py:53 證實：
```python
team_stats = {
    stat: sum_batter_stat(away_box, stat) + sum_batter_stat(home_box, stat)
    for stat in stat_cols
}
```

| 欄位 | corr w/ total_score | corr w/ home_win |
|---|---:|---:|
| H | 0.760 | **-0.110** |
| HR | 0.397 | 0.013 |
| 2B | 0.400 | -0.065 |
| BB | 0.366 | -0.009 |
| SO | -0.050 | -0.071 |

→ 這些欄位**對 total_score 有用，對 home_win 無用**。要拆主/客必須重抓 raw JSON。

### 2.7 時間效應
**Day of week** (N≥35)：Sunday 64.4%, Saturday 60.3%, Friday 49.3%, Wednesday 33.3% (注意 N 小的 Mon/Thu 不要過讀)。
**Month**: 八月 61.5%, 十月 71.4% (N=14 警告); 其他月份 45-55%。
→ 可考慮加 `is_weekend`, `month` 當 control，但只是 nuisance feature 不是核心。

### 2.8 Raw JSON 結構（金礦）
每場 game record 含：
```
seasonId, season, seq, date, stadium,
awayTeamId, awayTeam, awayScores,
awayBatterBox,   ← list of dicts, ~17 batters/game
awayPitcherBox,  ← 投手出場記錄
awayPAList,      ← 逐打席記錄
homeTeamId, homeTeam, homeScores,
homeBatterBox,
homePitcherBox,
homePAList
```
**batterBox 每位 batter 的 24 欄**：
```
order, playerId, playerNumber, playerName,
PA, AB, R, H, RBI, 2B, 3B, HR,
GIDP, DP, TP,
BB, IBB, HBP,
SO, SH, SF,
E, SB, CS
```

---

## 3. 「打者狀態 (Batter State)」定義

> *「在比賽 t 開打前，這支隊伍的打線整體可預期生產力，以及關鍵打者的近況」*

**核心原則 — Time-leakage discipline**：所有 rolling / cumulative 統計必須**只用 t 之前**的比賽，**絕不可**包含當場 (`compute_elo()` / `compute_pythagenpat()` 已示範 `lag(cumsum)` 模式)。

### 3.1 個別打者層 (Per-player, per-game) — 來源：raw JSON `*BatterBox`

| Tier | 欄位 | 計算式 | 用途 |
|---|---|---|---|
| **A. Season-to-date 累積** | `pp_season_PA` | cumulative PA before game t | 樣本量信心 |
| | `pp_season_AB` | cumulative AB | 分母 |
| | `pp_AVG_ytd` | `H/AB` (排除 BB+HBP+SF) | 打擊率 |
| | `pp_OBP_ytd` | `(H+BB+HBP)/(AB+BB+HBP+SF)` | 上壘率 |
| | `pp_SLG_ytd` | `(1B+2*2B+3*3B+4*HR)/AB`，其中 `1B = H-2B-3B-HR` | 長打率 |
| | `pp_OPS_ytd` | OBP + SLG | 綜合進攻 |
| | `pp_ISO_ytd` | SLG - AVG | 純長打 |
| | `pp_K_pct_ytd` | SO/PA | 三振率 |
| | `pp_BB_pct_ytd` | BB/PA | 選球能力 |
| **B. 近期狀態 (rolling)** | `pp_AVG_last7` | 過去 7 場累計 H/AB | hot/cold streak |
| | `pp_OPS_last14` | 過去 14 場 OBP+SLG | 中期狀態 |
| | `pp_OPS_last30` | 過去 30 場 | 長期狀態 |
| | `pp_games_since_HR` | 距上次全壘打場數 | streak |
| **C. Splits** | `pp_OPS_at_stadium` | 在這座球場的 career OPS | 球場熟悉度 |
| | `pp_OPS_vs_opp_team` | 對該對手隊的 career OPS | 對戰歷史 |
| | `pp_home_OPS / pp_away_OPS` | 個人主客場 split | 旅行 / 自家球場 |
| **D. Usage** | `pp_rest_days` | 距上一場出賽天數 (cap 5) | 疲勞 |
| | `pp_consec_games` | 連續出賽場次 | 疲勞 |
| **E. Lineup context** | `pp_order` | 1-9 (從 batterBox 取) | 打序位置 |
| | `pp_is_top_order` | order ∈ {1,2,3,4} | 核心打者標記 |

### 3.2 隊伍層彙總 (Team-game level) — **預測 home_win 直接可用**

對每場比賽 t，分別為主隊與客隊產出：

| 欄位 | 計算式 | 為什麼有用 |
|---|---|---|
| `team_runs_30g` | 過去 30 場該隊得分總和 | 得分能力 |
| `team_runs_per_game_30g` | runs_30g / N (N=過去場數，最多 30) | 標準化得分能力 |
| `team_AVG_30g` | sum(H) / sum(AB)，過去 30 場 | 整隊打擊率 |
| `team_OBP_30g` | (sum_H + sum_BB + sum_HBP) / (sum_AB + sum_BB + sum_HBP + sum_SF) | 整隊上壘 |
| `team_SLG_30g` | sum_TB / sum_AB，TB = 1B+2*2B+3*3B+4*HR | 整隊長打 |
| `team_OPS_30g` | OBP + SLG | 主訊號 |
| `team_ISO_30g` | SLG - AVG | 力量 |
| `team_K_pct_30g` | sum_SO / sum_PA | 揮空傾向 |
| `team_BB_pct_30g` | sum_BB / sum_PA | 選球紀律 |
| `team_HR_per_game_30g` | sum_HR / N | 全壘打火力 |
| `team_at_stadium_OPS_30g` | 該隊在本球場過去 30 場 (含主客) 的 OPS | 球場熟悉度 |
| `team_lineup_avg_OPS` (進階) | 賽前 starting 9 人 (從 PAList 推第 1 局打席順序) 的 weighted-mean YTD OPS，weights = [0.13, 0.13, 0.13, 0.12, 0.11, 0.10, 0.10, 0.09, 0.09] (Linear Weights) | 真實當日打線預期 |

### 3.3 對戰 diff feature (派生)

| 欄位 | 計算式 | 為什麼有用 |
|---|---|---|
| `diff_OPS_30g` | home_team_OPS_30g - away_team_OPS_30g | 進攻差距 |
| `diff_HR_per_game_30g` | home - away | 火力差距 |
| `diff_K_pct_30g` | home - away | 揮空差 (越大主隊越容易) |
| `diff_runs_per_game_30g` | home - away | 平均得分差 |
| `diff_lineup_OPS` (進階) | home_lineup - away_lineup | 當日打線預期差 |

### 3.4 m1-m7 模型整合建議

| 模型 | 現有 baseline 變數 | + 打者狀態 |
|---|---|---|
| m1 | intercept (HFA only) | 不加 |
| m2 | + stadium | 不加 (純球場效應) |
| m3 | + weather | 不加 |
| m4 (= m1+stadium) | + stadium | 不加 |
| m5 (= m1+weather) | + weather | 不加 |
| m6 (= stadium+weather) | + both | 不加 |
| m7 (Full) | + both | **加 diff_OPS_30g, diff_HR_per_game_30g, diff_K_pct_30g, team_at_stadium_OPS_30g** |
| **m7+ (新)** | m7 + Elo + Pythag + Rest + 打者狀態 | **完整 model 提交組員** |

→ **建議在 charter 補一個 `m7+` 或 `m8`**，把「打者狀態」當作新 feature group 跟 stadium / weather 並列做 ablation。組員若主張只在 m7 改 — 也 OK，但效應就會被混入 full model 變數 collinearity。

---

## 4. 立即下一步 (Sub-Agent 2 待辦)

1. **寫 `R/load_cde52470_data.R`** — 從本地 `data/raw/cde52470_mirror/` 載入並 normalize 成 charter schema (rename / stadium short-name)。
2. **寫 `R/parse_batterbox.R`** — 從 raw JSON 取出每場 home/away batterBox，rollup 成 team-game-level `team_OPS_30g` 等 §3.2 欄位。
3. **寫 `R/fetch_cwa.R`** — 從 CWA OpenData 抓 2024 賽季 360 場比賽 game-time 天氣，stadium-station 對應要擴成 11 球場（charter §10 只有 7 個）。
4. **更新 charter §10** — stadium roster 從 7 改 11，補天母 / 花蓮 / 嘉義 / 臺東 / 斗六 station mapping。
5. **建議組員加新模型 m7+** — 把「打者狀態 5 個 diff feature」當第三類變數做 ablation。

## 5. 資料局限與風險

| 風險 | 說明 | mitigation |
|---|---|---|
| **單季資料 N=360** | 樣本太小，cv fold 容易 unstable | 補抓 2022-2023 raw JSON (Rebas) |
| **小球場 N<10** | 花蓮/嘉義/臺東/斗六 home_win_rate 不可信 | level merging 或 `is_minor_venue` flag |
| **新莊 home_win 42.6%** | 富邦在自家反而輸 → 模型可能學到 stadium=新莊 ⇒ home 劣勢，但這其實是隊伍弱 | Elo / Pythag feature 已用「主隊強度」coefficient 分離掉，要驗證 |
| **天氣完全缺** | m3/m5/m6/m7 都跑不動 | 強制阻塞，先補 CWA |
| **H/HR 是合計** | 對 home_win 預測無用 | 回 raw JSON 重 aggregate |
| **打者狀態時間外漏風險** | 一不小心就把當場資料 leak 進 rolling | 嚴格 `lag(cumsum)` shift，照 `R/elo_pythag.R` 模式 |

---

*Auditor: Sub-Agent 2 (data-collector). 下一步交棒 Sub-Agent 3 (eda-explorer) 做進一步分組統計 + Park Factor 計算 + PCA on weather (待 CWA 抓完)。*
