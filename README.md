# CPBL Home-Team Win Prediction (114-2 Data Science)

Predict whether the home team wins a CPBL game from pre-game features
(team strength, batter state, stadium, weather). Single binary target
`is_home_win` ∈ {0, 1}; charter spec in `Results/01_define_the_goal.md`.

**Canonical pipeline = Python** (in `scripts/`). R lives in `R/` as
runnable mirrors (`R/mirrors/`) + the legacy Phase A POC (`R/poc/`) that
the GitHub Actions smoke test exercises.

---

## Quick start

```bash
# 1. Unzip a rebas release under data/raw/ (step1 globs for any season)
#    https://github.com/rebas-tw/rebas.tw-open-data/releases/tag/v0.1.0-2024
mkdir -p data/raw/rebas_v0.1.0-2024
cd data/raw/rebas_v0.1.0-2024
for f in CPBL-2024-OpenData.zip CPBL-2024-Challenge-OpenData.zip \
         CPBL-2024-TaiwanSeries-OpenData.zip; do
  curl -sL -O "https://github.com/rebas-tw/rebas.tw-open-data/releases/download/v0.1.0-2024/$f"
  unzip -q "$f"
done
cd -

# 2. Install deps
pip install -r requirements.txt

# 3. Run end-to-end (steps 1 -> 1b -> 2 -> 3)
python3 scripts/run_all.py
```

Outputs land in `Results/eval/*.csv`, `Results/eval/_final_metrics.json`,
`Results/figures/*.png`, and `models/best_model.joblib`.

---

## Repository layout

```
scripts/                      Python — the canonical pipeline
├── run_all.py                  one-shot orchestrator (git log -1 + step1..3)
├── step1_build_raw_games.py    rebas JSON -> raw_games.csv (any season, auto-discover)
├── step1b_fetch_weather.py     Open-Meteo Archive (no API key) -> games_with_weather.csv
├── step2_features.py           Elo / Pythag / rest / batter-state (30g) / park factor / diff
├── step3_models.py             m1..m7 ablation + 6-algo comparison + tuning + calibration
└── eda_cde52470_audit.py       (historical) EDA on the cde52470 mirror — kept for cross-check

R/                            R code, organised by purpose
├── elo_pythag.R                shared utility (used by mirrors + POC)
├── mirrors/                    runnable R re-implementations of the Python pipeline
│   ├── load_rebas_data.R         mirror of scripts/step1_build_raw_games.py
│   ├── compute_features.R        mirror of scripts/step2_features.py
│   ├── fetch_cwa.R               mirror of scripts/step1b_fetch_weather.py (Open-Meteo)
│   └── 03_build_models.R         mirror of scripts/step3_models.py
└── poc/                        legacy Phase A POC (synthetic smoke test for CI)
    ├── 00_synthetic_smoke.R      writes data/processed/synthetic_games.csv
    ├── 03a_phase_a_poc.R         entry point: m1..m7 over synthetic_games.csv
    ├── build_recipes.R           tidymodels recipes for m1..m7
    ├── 00_session_info.R         dumps sessionInfo() for reproducibility
    └── colab_phase_a_poc.R       self-contained, single-file Colab notebook

reports/                      narrative deliverables (markdown)
├── 02a_cde52470_data_audit.md  EDA audit + 打者狀態 schema
├── 03_step1_to_step3.md        canonical step1-step3 report (Python pipeline + results)
└── progress.md                 running progress log

Results/                      canonical artefacts (committed)
├── 01_define_the_goal.md       Goal-definer charter
├── eval/                       *.csv metric tables + _final_metrics.json
└── figures/                    model_comparison.png, calibration.png, shap_summary.png

models/                       trained-model artefacts (best_model.joblib at runtime)

data/                         gitignored except .gitkeep + raw/_lookup/
├── raw/_lookup/stadium_to_station.csv   11-stadium normalize + lat/lon for Open-Meteo
├── raw/                        rebas zips + JSONs (gitignored; drop them in)
└── processed/                  pipeline outputs (gitignored)

docs/strategy_memo.md         model-builder strategic notes
.github/workflows/r-poc.yml   GitHub Actions smoke test against R/poc/
requirements.txt              Python deps (the canonical pipeline)
requirements.R                R deps fallback when renv.lock is absent
.claude/                      Claude Code agent definitions (six sub-agents) + settings
```

---

## Pipeline at a glance

```
rebas JSON zips                      CWA Open-Meteo (ERA5)
   │                                          │
   ▼                                          ▼
step1_build_raw_games.py          step1b_fetch_weather.py
   │ raw_games.csv  ────────────►   games_with_weather.csv
   │                                          │
   ▼                                          ▼
                step2_features.py
                  │ Elo (K=4, HFA+24, MoV)
                  │ Pythagenpat 30g (x=1.83)
                  │ rest_days (cap 5)
                  │ batter-state team-game 30g rolling
                  │ at-stadium OPS 30g
                  │ park factor (time-aware leave-one-out)
                  │ diff (home - away) features
                  ▼
              model_ready_data.csv
                  │
                  ▼
                step3_models.py
                  ├ ablation m1..m7 (algorithm fixed = logistic; features vary)
                  ├ 6-algorithm comparison @ m7 (logit, glmnet, RF, XGB, LGB)
                  ├ TimeSeriesSplit grid tune top-4
                  ├ one isotonic calibration on train+valid
                  └ dual-threshold report (0.50 + Youden-J)
                  ▼
        Results/eval/{predictions,results_*,_final_metrics}
        Results/figures/{model_comparison,calibration,shap_summary}.png
        models/best_model.joblib
```

---

## CI

`.github/workflows/r-poc.yml` runs `R/poc/00_synthetic_smoke.R` then
`R/poc/03a_phase_a_poc.R` on Ubuntu R-4.4.1 for every push to
`claude/**` and every PR to `main`. It is a structural smoke test only —
synthetic data carries no predictive signal.

The Python pipeline is currently run **locally / in Colab** (no Python
CI configured yet); add `scripts/run_all.py --smoke` for a CI hook when
deps shrink to fit Actions cache.

---

## Conventions

- Time-aware splits only (`rsample::initial_time_split` or
  `sklearn.TimeSeriesSplit`) — never random shuffles.
- All rolling/cumulative features use prior-game-only `lag(cumsum)` —
  no t-leakage.
- Indoor games (`大巨蛋`) keep weather as climate context with
  `is_indoor = 1` so the model can down-weight.
- All times in `Asia/Taipei`; convert to UTC only at API boundaries.
- `data/` is gitignored except `_lookup/` and `.gitkeep`; raw data is
  WORM (write once, never mutate).

---

## Provenance

Generated under [Claude Code](https://claude.ai/code). Session traces
referenced in commit messages.
