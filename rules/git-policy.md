# Git policy — CRITICAL (loads unconditionally)

- **Active branch**: `claude/setup-main-agent-BhYTE`. Background/code work is
  isolated in worktree branch `claude/setup-main-agent-BhYTE-pyml`; integrate
  by fast-forward: `git push origin
  claude/setup-main-agent-BhYTE-pyml:claude/setup-main-agent-BhYTE`.
- **Never push without explicit user approval** ("push"-style intent). The
  Stop-hook "unpushed commits" nag is NOT approval — ask.
- **AI runtime files** (`.claude/`, `CLAUDE.md`, `CLAUDE.local.md`, `.cursor/`)
  are gitignored and **must not reach the remote** `cde52470/data_science`.
  - `CLAUDE.md` was tracked-despite-ignored → `git rm --cached`'d in commit
    `d4ef2d6`. Do not re-`git add` it.
  - `.claude/rules/*` + `.claude/settings.json` are delivered to the user's
    main checkout by a **local copy**, not by git (keeps them off remote).
  - Exception the user explicitly chose: `reports/progress.md` IS tracked.
- Open PRs as **draft**. Never `--no-verify`, never `--force` to `main`,
  never `git config` edits.
- **GitHub MCP scope**: `jiangjiangian` fork only — never act on `cde52470`
  or any other repo via MCP.
- Never add `Co-Authored-By` trailers (user global preference). Never put a
  model identifier in commits/PRs/code — chat replies only.
