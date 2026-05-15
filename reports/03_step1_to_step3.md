# Step 1 → Step 3 — CPBL Home-Win Prediction (Python Pipeline + Results)

> Branch: `claude/setup-main-agent-BhYTE`
> Updated: 2026-05-15
> Status: **Python is now the canonical pipeline** (instructor approved Python).
> R scripts demoted to reference mirrors. R Shiny = thin presentation layer
> that reads precomputed artifacts (no reticulate).

---

## 0. Architecture decision (this update)

| Was | Now |
|---|---|
| R `tidymodels` primary; Python POC | **Python primary** (tidymodels too slow in Colab) |
| Weather via `R/fetch_cwa.R` (CODiS, kept failing on stale `station_id`) | **`scripts/step1b_fetch_weather.py`** — Open-Meteo Archive, stdlib-only, NO API key |
| R Shiny computes predictions | Python precomputes `predictions.csv` + `best_model.joblib`; **Shiny only renders** |
| Single hardcoded 2024 path | step1 **auto-discovers any season** under `data/raw/` |

Execution environment: **Colab only**. Local Mac has no `pandas`; the
Anthropic sandbox is blocked from Open-Meteo (HTTP 403). Colab has the full
stack, reaches Open-Meteo, and can `git pull/push`.

One-shot: `python3 scripts/run_all.py` (prints `git log -1` first so a stale
checkout can never silently run old code again).

---

## Step 1 — Data acquisition

### 1.1 Source — rebas, multi-season ready

`scripts/step1_build_raw_games.py` now **globs every `CPBL-*OpenData*.json`
under `data/raw/`** and tags game_type/season from the filename. Drop in more
release zips and they are picked up with **zero code change**.

rebas releases that exist (checked 2026-05-15):

| Release | Content |
|---|---|
| `v0.1.0-2024` | 2024 全年 (regular + challenge + Taiwan series) — **currently used** |
| `v0.1.0-2023.1` | 2023 下半季 — *drop in to ~double N* |
| `v0.1.0-2023.0` | 2023 上半季 — *drop in to ~double N* |
| ~~2022~~ | **no release exists** |

> **#1 accuracy lever:** adding the two 2023 zips takes N from 366 → ~700+,
> which shrinks the noisy N=47 holdout to ~150 and beats any algorithm tweak.
> Just unzip them into `data/raw/` and rerun `run_all.py`.

### 1.2 Ingestion + the combined-batterbox bug fix

`homeBatterBox` / `awayBatterBox` aggregated **separately** (the cde52470
cleaned CSV summed them, making H/HR/etc. useless for home-win prediction —
corr |r|<0.11). 2024 alone → **366 games** (2 ties dropped).

### 1.3 Stadium normalize

Minor venues (花蓮/嘉義/臺東/斗六, each N<10 in 2024) collapse into `其他`.
Park-factor highlights: 澄清湖 PF≈1.18 (hitter park), 天母 ≈0.86 (pitcher
park). Lookup: `data/raw/_lookup/stadium_to_station.csv` (now carries
lat/lon for Open-Meteo).

### 1.4 Weather — `scripts/step1b_fetch_weather.py`

Open-Meteo Archive API (ERA5 reanalysis, ~10 km, hourly, **no API key**).
Per distinct stadium it pulls the full season window once, disk-caches the
JSON under `data/raw/.cache_weather/`, then joins game-hour →
`temperature, humidity, wind_speed, wind_dir, precip (+ wind_dir_cat)`.
Indoor (`大巨蛋`) games keep `is_indoor=1` so the model can down-weight
weather there. Graceful: a failed site → NA for its games (never crashes).

> **觀測 vs 氣候:** observation (game-time hourly) is what we need; ERA5
> already ingests CWA station data. Long-term 氣候 normals are optional
> anomaly features — not required for v1.

---

## Step 2 — Feature engineering

`scripts/step2_features.py` reads `games_with_weather.csv` if present (else
`raw_games.csv`), so weather rides straight through to
`model_ready_data.csv`. All rolling/cumulative features are strictly
**pre-game** (prior-game-only `lag(cumsum)` pattern; no t-leakage).

| Group | Features |
|---|---|
| Team strength | `diff_elo` (K=4, HFA+24, MoV), `diff_pythag` (30g, exp 1.83), `diff_rest` (cap 5), `pf_pre` (time-aware leave-one-out) |
| Batter state (打者狀態) | 30g rolling per side → diff of OPS/HR_per_g/K%/BB%/runs_per_g + `diff_at_stadium_OPS` |
| Weather | `temperature, humidity, wind_speed, precip`, `is_indoor` |
| Stadium | `stadium` (categorical) |

`features_complete` flags rows past the 30-game warm-up (≈248/366 for 2024).

---

## Step 3 — Modelling

### 3.1 Time-aware split (never random)

```
train = date < 2024-08-01
valid = 2024-08-01 .. 2024-09-15
test  = >= 2024-09-16   (held out; untouched in fit)
```

### 3.2 Ablation m1..m7 — algorithm FIXED (logistic), features VARY

This is the textbook way to read each group's marginal contribution.
**Charter §2 updated to match this scheme.**

| Model | Features | Question it answers |
|---|---|---|
| m1 | intercept only | pure home-field advantage baseline |
| m2 | stadium | does the venue alone predict? |
| m3 | weather | does climate alone predict? |
| m4 | team strength | Elo/Pythag/rest/PF alone |
| m5 | batter state | rolling lineup form alone |
| m6 | stadium + weather | charter "environment-full" |
| m7 | **FULL** (all four groups) | best feature set |

### 3.3 Algorithm comparison — features FIXED (full m7), algorithm VARIES

`logit, glmnet(l2), glmnet(elasticnet), RandomForest, XGBoost, LightGBM`,
each tuned with `TimeSeriesSplit(5)` `GridSearchCV`.

> **Winner is chosen by CV-AUC, NOT holdout.** N_test is tiny and noisy;
> every holdout AUC is reported with a 95% bootstrap CI so the reader sees
> the uncertainty instead of a false-precision point estimate.

### 3.4 One calibration + dual threshold

- **Isotonic** calibration via `TimeSeriesSplit` CV on train+valid (one
  technique only — stacking / extra calibration layers are noise at this N).
  Served only if it lowers holdout Brier vs raw.
- Threshold from **leak-free trainval OOF** (Youden's J). Holdout reported
  at **both** 0.50 and the tuned threshold side-by-side — never silently
  swapped.

### 3.5 Results

- **Run A (baseline, pre-weather, sandbox, logistic ablation, N=366):**
  tuned Random Forest holdout AUC ≈ 0.656; CV-AUC XGB/LGB/RF ≈ 0.58 (within
  ±0.07 at N=47); sigmoid calibration regressed to 0.536 (small/atypical
  playoff test set → motivated the isotonic-CV switch). SHAP top features:
  `diff_elo`, `diff_OPS_30g`, `diff_at_stadium_OPS`, `diff_runs_per_g_30g`,
  `diff_K_pct_30g`, `pf_pre` — **打者狀態 features confirmed to pay off**.
- **Run B (this pipeline, weather wired, isotonic-CV, dual threshold):**
  regenerated by `run_all.py` in Colab. Numbers land in
  `Results/eval/_final_metrics.json` / `results_*.csv` and the figures.
  Compare m3/m6/m7 AUC with-vs-without weather to quantify the weather
  group's contribution (the open question Run A could not answer).

---

## Step 3 outputs — Shiny precompute contract (decided up-front)

R Shiny does **zero computation** — it renders these:

| Artifact | Use |
|---|---|
| `Results/eval/predictions.csv` | leak-free per-game OOF `p_home_win` for the whole post-warmup season + `pred_at_0.5`, `pred_at_<thr>`, `is_holdout` — Shiny's main data source |
| `models/best_model.joblib` | `{model, features, categorical, numeric, threshold, winner}` — production scoring (a future `predict_today.py`, not reticulate) |
| `Results/eval/feature_schema.json` | winner, params, feature groups, stadium levels, CV/holdout AUC + CI — Shiny input form contract |
| `Results/figures/*.png` | model_comparison / calibration / shap_summary |

---

## How to reproduce (Colab — one shot)

```python
REPO = "/content/data_science_final_project"   # adjust if your path differs
import os, subprocess, sys
os.chdir(REPO)
subprocess.run(["git", "fetch", "origin"], check=True)
subprocess.run(["git", "reset", "--hard",
                "origin/claude/setup-main-agent-BhYTE"], check=True)
print(subprocess.run(["git", "log", "-1", "--oneline"],
                      capture_output=True, text=True).stdout)   # verify HEAD
# rebas zips must already be unzipped under data/raw/  (2024 [+ optional 2023])
subprocess.run([sys.executable, "scripts/run_all.py"], check=True)
# push regenerated artifacts back
subprocess.run(["git", "add", "-f",
                "Results/eval", "Results/figures"], check=False)
# (predictions.csv / feature_schema.json / _final_metrics.json all live
#  under Results/eval/, so the line above already covers them)
subprocess.run(["git", "commit", "-m", "data: Run B artifacts (weather)"],
               check=False)
subprocess.run(["git", "push", "origin",
                "HEAD:claude/setup-main-agent-BhYTE"], check=False)
```

Local R mirrors all live under `R/` (`R/load_rebas_data.R`,
`R/compute_features.R`, `R/03_build_models.R`) — kept for cross-checking
only; `scripts/` is Python-only and authoritative.

---

## File inventory (this round)

```
scripts/
  step1_build_raw_games.py    # multi-season auto-discover → raw_games.csv
  step1b_fetch_weather.py     # NEW — Open-Meteo, stdlib, no key
  step2_features.py           # auto-uses weather csv when present
  step3_models.py             # m1..m7 + algo + CV-winner + isotonic + Shiny artifacts
  run_all.py                  # NEW — one-shot orchestrator + stale-pull guard
R/  load_rebas_data.R · compute_features.R · fetch_cwa.R · elo_pythag.R   # reference mirrors
data/raw/_lookup/stadium_to_station.csv   # + lat/lon
reports/03_step1_to_step3.md  # this file
```

Gitignored (regenerated in Colab, force-added when curated):
`data/processed/*.csv`, `models/*.joblib`, `Results/eval/*`,
`Results/figures/*.png`, `data/raw/.cache_weather/`.

---

*Step 1 / 1b / 2 / 3 — Python canonical. Run B (weather) regenerates on the
next Colab `run_all.py`; R Shiny consumes the precomputed artifacts.*
