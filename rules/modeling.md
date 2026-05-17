# Modeling — the 7 progressive models (m1 → m7)

Ablation study to quantify each feature group's marginal contribution.
Algorithm is held **FIXED (logistic)** while the feature set varies — the
textbook way to read each group's value. Amended 2026-05-15 to add the two
extra groups (team-strength, batter-state) the team introduced. This file,
`scripts/step3_models.py`, and `reports/03_step1_to_step3.md` are kept
identical — if you change the scheme, change all three in one commit.

| Model | Features (target `is_home_win`) | Role |
|---|---|---|
| **m1** | intercept only | Baseline — pure home-field advantage |
| **m2** | stadium | Stadium-only |
| **m3** | weather (`temperature + humidity + wind_speed + precip`) | Weather-only |
| **m4** | team strength (`diff_elo + diff_pythag + diff_rest + pf_pre`) | Strength-only |
| **m5** | batter state (30g rolling OPS/HR/K%/BB%/runs diffs) | 打者狀態-only |
| **m6** | stadium + weather | Environment-full (original charter "full") |
| **m7** | **all four groups** | Full model |

- Every row is encoded from the home team's perspective, so "home/away" is
  folded into the intercept (m1) — the apples-to-apples baseline m2–m7 must
  statistically beat.
- Algorithm comparison (logit / glmnet / RF / XGB / LGB) runs **separately**
  on the fixed full m7 set. **Winner is picked by time-series-CV AUC, never
  the holdout** (N≈47, ±0.10 CI — holdout deltas are noise).
- One calibration only (isotonic via time-aware CV on train+valid). No
  stacking / no extra calibration layers — they overfit at this N.
- Dual-threshold reporting: holdout at 0.50 **and** the OOF-Youden threshold
  side-by-side; never silently swap.
