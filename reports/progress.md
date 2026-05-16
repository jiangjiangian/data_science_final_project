# Progress Log — CPBL Home-Win Prediction

> **Purpose:** durable, session-by-session project memory. The last ~60 lines
> are auto-injected into every Claude session via the `SessionStart` hook in
> `.claude/settings.json`, so any session resumes with full context.
>
> **Format:** newest entry on top. Each entry records what changed, the *why*
> behind decisions (the part not recoverable from `git log`/diffs), the commit,
> and the concrete next step. Update rule: `.claude/rules/progress-tracking.md`.
> Keep entries tight — this is a decision log, not a changelog of every edit.

---

## 2026-05-16 — 2023 data silently dropped: glob root-cause fixed

User flipped `USE_2023` but Cell 4 reported only 3 (2024) JSON and **did
not error**. Investigated with ground-truth zip inspection (not doc
assumptions). **Root cause:** the rebas 2024 release uses ASCII filenames
(`CPBL-2024-OpenData.json`); the **2023** release uses *Chinese* names
(`中職2023年-OpenData.json` / `中職2023年下半季-OpenData.json` /
`中職2023年-季後挑戰賽-OpenData.json` / `中職2023年-台灣大賽-OpenData.json`).
Both `step1.discover_sources` and notebook Cell 4 hard-globbed
`CPBL-*OpenData*.json` → every 2023 file silently skipped (no raise → the
bug was invisible). The URLs/tags were correct all along (GitHub-API
verified: tags `v0.1.0-2023.0`/`.1`, asset names exact).

**Fix:**
- `discover_sources`: glob `CPBL-*OpenData*` → `*OpenData*` (still excludes
  per-game `*-G<N>.json` — they lack the 'OpenData' token); `game_type`
  now also keys on Chinese 挑戰/台灣大賽; season regex `CPBL-(\d{4})` →
  `(20\d{2})`. Comment block documents why a `CPBL-*` prefix is wrong.
- `colab_run.ipynb`: same glob fix; `USE_2023` default **True** (single
  2024 is proven no-signal — no reason to default to it); per-zip subdir
  extraction; `assert ≥7 combined`; **NEW Cell 4b** pitcher-data
  diagnostic (prints schema + starter sanity; gates the pitcher code).
- Verified **locally** before push: AST-extracted the edited
  `discover_sources`, ran it on the real rebas filename set → 7 combined
  found, per-game decoys excluded, 2023+2024 + challenge/series tagged
  correctly. (macOS/OneDrive can't create CJK filenames via `unzip` —
  locale `Illegal byte sequence`; Colab Linux UTF-8 has no such issue.)

**Why default `USE_2023=True`:** Run B proved one 2024 season carries no
out-of-sample signal; defaulting the notebook to the no-signal config was
a footgun. The whole point now is N≈700 + the pitcher lever.

**Next:**
1. User re-runs notebook (Cell 2 `reset --hard` pulls this fix) → pastes
   **Cell 4b + Cell 6 JSON**. Cell 6 = the conclusive N≈700 2-group
   answer (does data alone move AUC off 0.5?).
2. On Cell 4b output: build leak-free starting-pitcher (starter =
   `order==1`, per-`playerId` rolling) + bullpen features into
   `step1`/`step2`; add **m6=pitching** to `step3`. m1–m7 scheme LOCKED:
   intercept / stadium / weather / team-strength / batter-state /
   **pitching** / full — change `modeling.md` + `reports/03` + `step3`
   in one commit. No scraper, no CWA key (rebas has pitcherBox; weather
   is the empirically worst group).

## 2026-05-16 — Run B complete: single 2024 season ≈ NO out-of-sample signal

Pipeline now runs end-to-end in Colab (fixed `cross_val_predict`→walk-forward
OOF, `3d808dc`; added `colab_run.ipynb` one-click, `7e57c5d`). User ran it
with weather, pushed artifacts (`8fca820`).

**The finding (honest, important):**
- **`season_oof_auc = 0.504`** over 205 leak-free walk-forward games — the
  largest-N, least-noisy metric. ≈ coin flip. No real signal.
- Ablation m1–m7 (logistic, test): m1 .500 / m2 stadium .504 / m3 weather
  **.436** / m4 strength .525 / m5 batter .429 / m6 env .467 / m7 full .455.
  **No feature group beats the home-field intercept.** Weather is the worst.
- Holdout tuned_rf .585 [.41,.74], tuned_xgb .589 [.42,.75] — CIs span
  random→good ⇒ noise. Run A's "0.656" was N=47 cherry-noise; the
  season-OOF + bootstrap CI (added precisely to catch this) confirm it.
- Calibration regressed again (.509<.585) → served raw. Correct logic.

**Why / interpretation:** single-game baseball is near-random without
starting-pitcher info; MLB SOTA pre-game ≈ .58–.60 with far more data. One
CPBL season, no SP features → ≈.50 is the expected, defensible answer. This
is a clean negative result the methodology *correctly* surfaces (not an
overclaim). Good DS narrative for the report.

**Next (decisive):**
1. **Don't chase it** — no more tuning/stacking; that's fitting noise.
2. Biggest lever: rerun notebook with `USE_2023=True` (N→~700, holdout
   →~150). Gives a *conclusive* tight-CI number, not signal-from-nothing.
3. Real modeling gap: **starting pitcher** features (check if rebas JSON has
   pitching box / probable starters). Only thing likely to move AUC.
4. Report should lead with `season_oof_auc`+CI and the ablation, framed as
   "no group beats HFA on one season; consistent with known near-randomness".

## 2026-05-15 — Python pivot + memory decomposition

**Context shift:** instructor approved Python; `tidymodels` proved too slow in
Colab. Project is now **Python-canonical**; R scripts demoted to reference
mirrors; R Shiny becomes a thin renderer of precomputed Python artifacts.

**Done (commit `e09b4ba`, branch `claude/setup-main-agent-BhYTE-pyml`):**
- `step1` auto-discovers any rebas season under `data/raw/` (rebas has
  2023.0 / 2023.1 / 2024; **no 2022**) — adding 2023 zips is the #1 accuracy
  lever (N 366 → ~700+, shrinks the noisy N=47 holdout).
- `step1b_fetch_weather.py` NEW — Open-Meteo Archive, stdlib-only, no API key;
  replaces `R/fetch_cwa.R` (kept failing on stale `station_id` in Colab).
  **Hard-fails** on unmapped stadium / >50% missing — never silently writes
  NA weather (the exact trap that burned the R version).
- `step2` auto-consumes `games_with_weather.csv`.
- `step3` rebuilt: m1–m7 redefined (4 feature groups), **winner by CV-AUC not
  the noisy N=47 holdout**, bootstrap CI, ONE isotonic-CV calibration,
  dual-threshold report, exports Shiny precompute contract
  (`predictions.csv` / `best_model.joblib` / `feature_schema.json`).
- `run_all.py` NEW — one-shot orchestrator; prints `git log -1` first so a
  stale Colab pull can never silently run old code again.
- Ablation scheme made consistent across code + `reports/03` + `CLAUDE.md §2`.
- CLAUDE.md decomposed into `.claude/rules/*.md` (env notes folded into
  `rules/environment.md`, not a `CLAUDE.local.md`); thin CLAUDE.md `@import`s
  them; this progress log added; `CLAUDE.md` `git rm --cached`'d (was tracked
  despite `.gitignore` — leaking to remote on every edit).
- **File architecture cleaned: `scripts/` = Python only, `R/` = all R.**
  `git mv`'d 5 `.R` files scripts→R (history preserved); fixed the one real
  breakage `source(here::here("scripts/00_session_info.R"))` → `R/...` plus
  stale comment/doc paths. Python stays in `scripts/` (moving it breaks
  `ROOT = parent.parent`).

**Decisions / why:**
- Winner by CV-AUC: holdout N=47 has ±0.10 CI; chasing holdout deltas is
  noise. Single calibration only — stacking/extra layers overfit at this N.
- Precompute Shiny contract (not reticulate): deploy-safe, course-friendly.
- progress.md → `reports/` (tracked, team-visible) per user choice, even
  though it slightly bends the "AI runtime off remote" policy.

**Next:**
1. ✅ DONE — pushed `6383172..be0c2bf` (FF) to
   `origin (jiangjiangian fork)/claude/setup-main-agent-BhYTE`
   (pipeline `e09b4ba` + memory `d4ef2d6` + reorg `be0c2bf`).
2. **Local decomposition not yet live in main checkout.** In the user's
   main checkout: `git fetch && git reset --hard
   origin/claude/setup-main-agent-BhYTE`, THEN copy
   `.claude/worktrees/pyml/{.claude/rules,.claude/settings.json,CLAUDE.md}`
   → main `.claude/` (gitignored local files; copy order matters — after
   reset). First new session will prompt to approve the SessionStart hook.
   After that, remove the stale worktree (`git worktree remove`).
3. In Colab: unzip rebas (2024 [+ optional 2023]) → `python3
   scripts/run_all.py` → push back `Results/eval/*` for **Run B** (weather)
   numbers; compare m3/m6/m7 AUC with-vs-without weather.
4. Sub-Agent 6: R Shiny skeleton reading the precompute artifacts.

---

## 2026-05-14 — Step 1–3 pipeline first build

- rebas v0.1.0-2024 ingested (regular+challenge+series → 366 games, 2 ties
  dropped). Fixed the cde52470 combined-batterbox bug (home+away summed →
  useless; now aggregated per side).
- Batter-state schema implemented: 27 cols of 30g team-game rolling
  (OPS/HR/K%/BB%/runs diffs + at-stadium OPS).
- Time-aware split; Elo (K=4, HFA+24, MoV) + Pythagenpat + rest + Park
  Factor. tuned RF holdout AUC ≈ 0.656; calibration regressed (small/atypical
  playoff test → motivated the later isotonic switch).
- CODiS weather failed (CAPTCHA/session) → rewrote `R/fetch_cwa.R` to
  Open-Meteo. Commits `708dba6`, `6383172`.

## 2026-05-13 and earlier

- `7e55426` cde52470 `data` branch audit + batter-state schema spec
  (`reports/02a`).
- `8935b67` self-contained Colab Phase-A POC.
- `ed7697b` colab-mcp server config.
