# Six-agent lifecycle, skills & MCPs

Six specialised sub-agents under `.claude/agents/`, mirroring the DS lifecycle:

```
1 Goal Definer → 2 Data Collector → 3 EDA
                                      ↓
6 Shiny Deployer ← 5 Evaluator ← 4 Model Builder
```

| # | Agent file | One-line job | Status |
|---|---|---|---|
| 1 | `01-goal-definer.md` | Lock question/target/thresholds | done |
| 2 | `02-data-collector.md` | rebas + weather, provenance | done (step1/1b) |
| 3 | `03-eda-explorer.md` | Park Factor, weather, missingness | done (reports/02a,03) |
| 4 | `04-model-builder.md` | POC → production pipeline | done (step3) |
| 5 | `05-model-evaluator.md` | Confusion/calibration/SHAP/fairness | partial (in step3) |
| 6 | `06-shiny-deployer.md` | `bslib` dashboard reading precompute artifacts | **next** |

Each agent file is self-contained (role, workflow, XML prompt). Invoke with
`@01-goal-definer …` or paste its XML prompt into a fresh session.

**Skills/MCPs**: `find-skills` (`.claude/skills/find-skills/`) discovers more
via `npx skills find <query>`. GitHub MCP scope = `jiangjiangian` fork only
(see git-policy). colab-mcp exists but needs an active browser session and
the user must approve the connection; don't auto-retry if rejected.
