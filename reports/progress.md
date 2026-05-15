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
