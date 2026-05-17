# Environment reality (which machine can run what)

| Where | ML libs | rebas/processed data | Open-Meteo | git | Verdict |
|---|---|---|---|---|---|
| **User's Mac** (where editing/commits happen) | ❌ no pandas | ❌ gitignored, absent | — | ✅ | edit / commit / push only |
| **Anthropic sandbox** | ✅ pandas/sklearn/xgb/lgb/shap | bring-your-own | ❌ HTTP 403 | ✅ | **can't fetch weather** → incomplete; ephemeral |
| **Colab** | ✅ full | ✅ (unzip rebas there) | ✅ | ✅ | **only place the full pipeline runs** |

- Run everything in **Colab**: `git reset --hard origin/<branch>` →
  `python3 scripts/run_all.py` → push `Results/eval/*` back.
- Colab path is sometimes doubled
  (`/content/data_science_final_project/data_science_final_project`) — the
  inner dir is the git repo; run from there.
- `run_all.py` prints `git log -1` first — always confirm the hash matches
  origin before trusting any output (a stale pull silently ran old code once).
- colab-mcp is configured but flaky: needs an open, logged-in Colab tab and
  explicit user approval of the connection; it disconnects on rejection.
