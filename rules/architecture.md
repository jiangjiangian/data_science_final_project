# Architecture — directory contract, data flow, variable schema

## Pipeline (Python-canonical)

```
data/raw/  (rebas JSON, gitignored — unzipped per season)
  └─ scripts/step1_build_raw_games.py     auto-discovers ANY CPBL-*OpenData*.json
       → data/processed/raw_games.csv      (per-side batterbox, ties dropped)
  └─ scripts/step1b_fetch_weather.py      Open-Meteo Archive (stdlib, no key)
       → data/processed/games_with_weather.csv   (HARD-fails, never silent-NA)
  └─ scripts/step2_features.py            Elo/Pythag/rest/PF + batter-state + weather
       → data/processed/model_ready_data.csv  ·  park_factors.csv
  └─ scripts/step3_models.py              m1–m7 + algo tune + isotonic + Shiny artifacts
  scripts/run_all.py                      one-shot; prints `git log -1` (stale-pull guard)
```

**Language separation (enforced):** `scripts/` is **Python only** (the
canonical pipeline); `R/` holds **every** `.R` file (reference mirrors +
helpers + utilities). Python step scripts must stay at `scripts/` depth —
`ROOT = Path(__file__).resolve().parent.parent` breaks if nested. R files use
`here::here()` (project-root anchored) so their location is free.

R mirrors (`R/load_rebas_data.R`, `R/compute_features.R`,
`R/03_build_models.R`, `R/elo_pythag.R`, `R/fetch_cwa.R`) are **reference
only** — the Python path is authoritative.

## Shiny precompute contract (decided up-front — Shiny does ZERO compute)

| Artifact | Use |
|---|---|
| `Results/eval/predictions.csv` | leak-free per-game OOF `p_home_win` + `pred_at_0.5` / `pred_at_<thr>` / `is_holdout` — Shiny's main data source |
| `models/best_model.joblib` | `{model, features, categorical, numeric, threshold, winner}` for future `predict_today.py` (NOT reticulate) |
| `Results/eval/feature_schema.json` | winner/params/feature-groups/stadium-levels/CV+holdout AUC+CI — Shiny input contract |
| `Results/figures/*.png` | model_comparison / calibration / shap_summary |

## Path policy

- `data/`, `models/`, `Results/eval`, `Results/figures` are gitignored;
  curated outputs are delivered with `git add -f` only.
- `reports/*.md` committable (incl. `reports/progress.md`); `*.html`/`_cache`
  ignored. `Results/` is the path-of-truth for sharing.

## Variable alignment

| Symbol | Type | Domain |
|---|---|---|
| `is_home_win` | int {0,1} | 1 if `home_score > away_score`; ties dropped |
| `stadium` | factor | 樂天桃園 / 洲際 / 天母 / 新莊 / 澄清湖 / 臺南 / 大巨蛋 / 其他 (11→8 collapsed) |
| `temperature` | numeric °C | ~15–38 |
| `humidity` | numeric % | 30–100 |
| `wind_speed` | numeric m/s | 0–15 |
| `wind_dir` / `wind_dir_cat` | numeric° / 8-pt compass | optional |
| `precip` | numeric mm | ≥0 |
| `is_indoor` | int {0,1} | 1 for 大巨蛋 (weather down-weighted) |
| `date` | Date | ISO 8601 |
| `game_id` | str | `{YYYYMMDD}-{TYPE3}-{seq:03d}` |
