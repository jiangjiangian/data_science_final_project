# Progress tracking — keep reports/progress.md current

`reports/progress.md` is this project's durable decision log. Its last ~60
lines are auto-injected at every SessionStart (hook in `.claude/settings.json`).

**When to update:** before declaring a session's substantive work done —
alongside making the deliverable durable (commit), add ONE entry. Substantive
= shipped code/docs, a decision, a pivot, a fixed root cause, a blocker.
Trivial Q&A or pure exploration → no entry.

**How:**
- Newest entry on **top**, under a `## YYYY-MM-DD — <headline>` heading.
- Capture the **why / decisions / blockers** — the part NOT recoverable from
  `git log` or the diff. Don't restate the diff.
- Include: what changed, key decisions + rationale, commit hash, the concrete
  **Next** step, and any pending approval (e.g. unpushed push).
- Tight prose. This is a decision log, not a changelog.
- It is tracked & on the remote (the one AI-adjacent file the user chose to
  share) — write it for a teammate, no secrets.

**Never** automate the *writing* via a `claude -p` hook — that recursion
blew up 302 sessions once. The SessionStart hook only *reads*; Claude writes.
