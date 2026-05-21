# CPBL Home-Team Win Prediction (114-2 Data Science)

Predict whether the home team wins a CPBL game from **pre-game**
features only (team strength, batter state, stadium, weather, pitching).
Binary target `is_home_win` ∈ {0, 1}; full charter in
`Results/01_define_the_goal.md`.

**Canonical pipeline = a single self-contained Colab notebook.**
`python/cpbl_pipeline.ipynb` (v1, locked) runs step1 → step1b → step2 →
step3 inline; `python/cpbl_pipeline_v2.ipynb` (v2, leak-free + paper
replication) is the current focus. R lives in `R/` as runnable mirrors
(`R/mirrors/`) and the legacy Phase A POC (`R/poc/`) that the GitHub
Actions smoke test exercises.

---

## Quick start (Colab)

1. Open **`python/cpbl_pipeline_v2.ipynb`** (or v1) in Colab.
2. `Runtime → Run all`. The notebook self-clones rebas 2023+2024,
   fetches Open-Meteo weather, builds features, trains m1–m7 +
   six-algorithm ablation, and writes every artefact under
   `Results/` / `models/`. No external `.py` is needed — the stadium
   lookup is embedded.

Local Python execution still works if you keep deps current:
```bash
pip install -r requirements.txt
jupyter notebook python/cpbl_pipeline_v2.ipynb
```

---

## Repository layout

```
python/                    Canonical Python pipeline (Colab notebooks)
├── cpbl_pipeline.ipynb         v1 — locked: step1..step3 inlined,
│                                Run All produces full Results/ tree
└── cpbl_pipeline_v2.ipynb      v2 — leak-free + paper replication
                                (Lo et al. 2025 AUC 0.97 is leakage
                                — v2 reproduces it then strips it)

R/                         R code, organised by purpose
├── elo_pythag.R              shared utility (used by mirrors + POC)
├── mirrors/                  runnable R re-implementations of the
│                              Python pipeline
│   ├── load_rebas_data.R
│   ├── compute_features.R
│   ├── fetch_cwa.R           Open-Meteo Archive (no API key)
│   └── 03_build_models.R
└── poc/                      legacy Phase A POC (CI smoke test)
    ├── 00_synthetic_smoke.R    writes data/processed/synthetic_games.csv
    ├── 03a_phase_a_poc.R       entry point: m1..m7 on synthetic data
    ├── build_recipes.R         tidymodels recipes for m1..m7
    ├── 00_session_info.R       dumps sessionInfo() for reproducibility
    └── colab_phase_a_poc.R     single-file Colab notebook (POC era)

reports/                   Narrative deliverables (markdown)
├── 00_final_report.md          final submittable report
├── 02a_cde52470_data_audit.md  EDA audit + 打者狀態 schema
├── 03_step1_to_step3.md        step1-step3 implementation report
├── progress.md                 running progress log
└── build_report_html.py        renders the final-report markdown to
                                a self-contained HTML with figures

Results/                   Canonical artefacts (committed)
├── 01_define_the_goal.md       goal-definer charter
├── eval/                       run-A metric tables + predictions.csv +
│                                feature_schema.json + _final_metrics.json
├── figures/                    run-A figures (model_comparison /
│                                calibration / shap_summary /
│                                ablation_holdout_vs_oof)
├── poc/                        Phase A POC artefacts
└── v2/                         v2 (leak-free + paper-replication)
    ├── eval/                     _final_metrics_v2.json, results_v2.csv,
    │                              _feature_lists.json, _leak_demo.json
    └── figures/                  leakage_demo.png + EDA (corr,
                                   distributions, pca) + pitch-level
                                   ablation

docs/                      Strategy notes
└── strategy_memo.md            model-builder strategic notes

data/                      Gitignored except _lookup/ and .gitkeep
├── raw/_lookup/                stadium_to_station.csv — 11-stadium
│                                normalize + lat/lon for Open-Meteo
├── raw/                        rebas zips + JSONs (gitignored)
└── processed/                  pipeline outputs (gitignored)

models/                    Trained-model artefacts at runtime
                            (best_model.joblib written by notebook)

.github/workflows/r-poc.yml   GitHub Actions smoke test against R/poc/
requirements.txt              Python deps for the notebooks
requirements.R                R deps fallback when renv.lock is absent
.claude/                      Claude Code agent definitions + settings
```

---

## Pipeline at a glance

```
rebas JSON zips (2023.0 + 2023.1 + 2024)        CWA via Open-Meteo (ERA5)
   │                                                    │
   ▼                                                    ▼
step1: parse JSON, re-aggregate batterBox &       step1b: Open-Meteo Archive,
       pitcherBox per side, normalize stadium             join to game-hour
   │ raw_games.csv  ──────────────────────────►   games_with_weather.csv
   │                                                    │
   ▼                                                    ▼
                step2: feature engineering
                  ├ Elo (K=4, HFA+24, MoV-adjusted)
                  ├ Pythagenpat 30g (x=1.83)
                  ├ rest_days (cap 5)
                  ├ batter-state team-game 30g rolling (OPS/HR/K%/BB%/runs)
                  ├ at-stadium OPS 30g
                  ├ park factor (time-aware leave-one-out)
                  ├ starter own-form (last-5) + staff 30g
                  └ diff (home - away) features
                  ▼
              model_ready_data.csv
                  │
                  ▼
                step3: m1..m7 ablation + 6-algorithm comparison
                  ├ time-aware walk-forward OOF (never random shuffle)
                  ├ TimeSeriesSplit grid tune
                  ├ isotonic calibration on train+valid
                  └ dual-threshold report (0.50 + Youden-J)
                  ▼
        Results/eval/  Results/figures/  Results/v2/  models/best_model.joblib
```

m1..m7 ablation scheme (algorithm fixed = logistic; features vary):

| Model | Features | Question it answers |
|-------|----------|---------------------|
| m1    | intercept only           | pure home-field advantage baseline |
| m2    | stadium                  | does the venue alone predict? |
| m3    | weather                  | does climate alone predict? |
| m4    | team strength            | Elo / Pythag / rest / PF alone |
| m5    | batter state             | rolling lineup form alone |
| m6    | **pitching**             | starter-L5 + staff-30g alone |
| m7    | FULL                     | best feature set |

---

## CI

`.github/workflows/r-poc.yml` runs `R/poc/00_synthetic_smoke.R` then
`R/poc/03a_phase_a_poc.R` on Ubuntu R-4.4.1 for every push to
`claude/**` and every PR to `main`. It is a structural smoke test only —
synthetic data carries no predictive signal.

There is no Python CI yet — the notebooks are run in Colab end-to-end
(faster than spinning up Actions caches for sklearn / xgboost / lightgbm
/ shap on every push).

---

## Conventions

- **Time-aware splits only.** Never `initial_split()`,
  `train_test_split(shuffle=True)`, or random k-fold over time-ordered
  games — use `initial_time_split()` /  `TimeSeriesSplit` /
  walk-forward OOF.
- **No t-leakage.** All rolling/cumulative features use prior-game-only
  `lag(cumsum)`. Verified per feature in the notebook diagnostics.
- **Indoor games (大巨蛋)** still record outdoor weather but flag
  `is_indoor = 1` so the model can down-weight or zero out.
- All times in `Asia/Taipei`; convert to UTC only at API boundaries.
- `data/` is gitignored except `_lookup/` and `.gitkeep`. Raw data is
  WORM — written once, never mutated.

---

## Provenance

Generated under [Claude Code](https://claude.ai/code). Session traces
referenced in commit messages.
