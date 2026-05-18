# `.claude/agents/` — CPBL Sub-Agent Index

This folder contains six Claude Code sub-agents, one per data-science
lifecycle step, plus this index. They are **gitignored** so AI runtime
files never reach the public repo.

## How to invoke

In Claude Code (CLI or Desktop):

```text
@goal-definer    
@data-collector  
@eda-explorer   
@model-builder   
@model-evaluator 
@shiny-deployer 
```

In **claude.ai / web** (this surface), you can paste the *Polished XML
Prompt* section from any agent file into a fresh conversation — every
agent file is self-bootstrapping.

## Inventory

| # | File | Frontmatter `name` | Model | Role |
|---|---|---|---|---|
| 1 | `01-goal-definer.md` | `goal-definer` | opus | Charter + success thresholds + risk register |
| 2 | `02-data-collector.md` | `data-collector` | opus | CPBL + CWA crawler with provenance |
| 3 | `03-eda-explorer.md` | `eda-explorer` | opus | Park Factor, PCA, missingness, weather × runs |
| 4 | `04-model-builder.md`  | `model-builder` | opus | **Phase A POC → Phase B `tidymodels` production** |
| 5 | `05-model-evaluator.md` | `model-evaluator` | opus | Confusion / calibration / SHAP / fairness |
| 6 | `06-shiny-deployer.md` | `shiny-deployer` | opus | `bslib` dashboard + deploy |

## Hand-off contract

```
goal-definer ──▶ ????????????
                        │
                        ▼
data-collector ──▶ ????????????
                        │
                        ▼
eda-explorer ────▶ ????????????
                        │
                        ▼
model-builder ───▶ ????????????
                        │
                        ▼
model-evaluator ─▶ ????????????
                        │
                        ▼
shiny-deployer ──▶ ????????????
```

Each downstream agent **must** consume only the documented hand-off
files. No reaching upstream into earlier agents' working notes.

## Skills installed in this repo

| Skill | Where | Purpose |
|---|---|---|
| `find-skills` | `.claude/skills/find-skills/SKILL.md` | Search & install further skills via `npx skills find <query>` |

Future installs (suggested):

```bash
# inside Claude Code, ask: "find me a skill for <X>"
npx skills find tidymodels
npx skills find shiny-best-practices
npx skills find shap
npx skills find rvest-scraping
```

## MCP servers in use

| Server | Scope | Notes |
|---|---|---|
| (others may attach during a session) | — | List via ToolSearch |

## Conventions inherited from `CLAUDE.md`
- create a single perfect ipynb first. Until the whole pipeline is totally completelly, then transform it into R
- Tidyverse Style Guide.
- `here::here()` for paths; no `setwd()`.
- Secrets via `.Renviron`; never hard-coded.
- 繁體中文 narrative comments; English code.
- Time-aware splits on game data — never `initial_split()`.
- All AI runtime files (this folder, `CLAUDE.md`, etc.) **gitignored**.