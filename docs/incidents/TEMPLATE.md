# Incident: <short title>

Copy this file to `docs/incidents/YYYY-MM-DD-<service>-<short-slug>.md` and
fill it in. Blameless: describe what the system and the responders did, not
who's at fault. If a step here doesn't apply, write "N/A" rather than
deleting it — a missing section reads as "forgotten," not "not applicable."

- **Service:** `<name>` (`services/<name>/service.yaml`)
- **Severity:** <page / ticket>
- **Status:** <ongoing / resolved>
- **Date:** YYYY-MM-DD
- **Author(s):**

## Summary

Two or three sentences: what broke, for whom, for how long. Written so
someone who wasn't in the incident understands the shape of it without
reading further.

## Impact

- User-facing effect: <e.g. elevated 5xx rate on GET /work, degraded p99 latency>
- Duration: <first alert to resolution>
- Scope: <all traffic / a subset — and how you know>
- SLO/error-budget effect: pull the actual number, don't estimate —
  `1 - (<service>:sli_error_ratio:rate30d / <budget>)` from the dashboard's
  "Error budget remaining" panel, before and after.

## Timeline

All timestamps UTC. One line per event; link the alert, PR, commit, or
dashboard panel where relevant instead of re-describing it in prose.

| Time (UTC) | Event |
|---|---|
| | Change merged/deployed (the actual root cause, once known — fill in retroactively) |
| | Alert fires: `<AlertName>` — detection |
| | Responder acknowledges |
| | Impact confirmed via dashboard/query |
| | Root cause identified |
| | Mitigation applied (e.g. `git revert` pushed) — mitigation |
| | ArgoCD sync completes, alert clears — resolution |

- **Time to detect** (change → alert fires):
- **Time to mitigate** (alert fires → mitigation pushed):
- **Time to resolve** (alert fires → alert clears):

## Root cause

What actually changed, and why it produced this effect. Link the commit
(`git log -- services/<name>/service.yaml`) or PR. If the mechanism isn't
fully understood yet, say so explicitly rather than guessing — "root cause
unknown, under investigation" is a valid and honest state for this section.

## How it was fixed

The exact rollback procedure that was followed (see
`docs/runbooks/<name>.md`) — commands run, not just "we reverted it."

```
git revert --no-edit <sha>
platformctl render <name>
git push
```

## Detection

How was this caught? Which alert, and did it fire promptly given the
burn-rate windows it uses? If it was caught by a person noticing before any
alert fired, say that — it's a gap in the alert, not a win.

## What went well

Concrete, specific. "The gitops-revert rollback worked as documented and
took N minutes start to finish" is useful; "communication was good" is not.

## What didn't go well

Same standard — specific and checkable, not a vague feeling. Include gaps
in monitoring, runbook steps that didn't match reality, and anything that
took longer than it should have.

## Action items

Every item has an owner and is either a follow-up issue link or a specific
next step — "investigate further" is not an action item.

| Action | Owner | Status |
|---|---|---|
| | | not started / in progress / done |
