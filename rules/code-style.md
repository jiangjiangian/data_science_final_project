---
paths:
  - "scripts/**/*.py"
  - "scripts/**/*.R"
  - "R/**/*.R"
  - "app/**/*.R"
---

# Code conventions (path-scoped: loads when source files are opened)

1. **Python is canonical; R mirrors are reference.** New analysis goes in
   `scripts/*.py`. Keep R mirrors only if cheap; never block on R.
2. **snake_case, ≤ 80 cols.** Python ≈ PEP 8; R ≈ tidyverse style, `<-` for
   assignment.
3. **Paths**: Python `Path(__file__).resolve().parent.parent`; R
   `here::here()`. Never `setwd()` / absolute paths / `os.chdir` in library code.
4. **Weather/HTTP fetchers: stdlib-only where feasible** (`urllib`, `json`) —
   Colab has no guaranteed extra installs and the sandbox blocks Open-Meteo.
5. **Secrets** via env (`os.environ` / `Sys.getenv`), never hardcoded.
   `.Renviron` gitignored. Open-Meteo needs NO key (don't reintroduce one).
6. **Time-aware splits ONLY** — never random split on game data. Train <
   2024-08-01 / valid → 09-15 / test ≥ 09-16. All rolling features are
   strictly prior-game (`lag(cumsum)`); a t-leak is a correctness bug.
7. **Fail loud, never silent.** Data joins that can drop rows must hard-fail
   (see `step1b` SystemExit guards) — the R `fetch_cwa.R` silent-NA wasted a
   whole Colab session.
8. **Comments**: 繁體中文 for domain logic, English for code mechanics.
9. **Reproducibility**: deterministic seeds (`RNG=42`); pin deps; one-shot is
   `scripts/run_all.py`.
