# Runbook: demo-api

Referenced by every alert in `observability/rules/demo-api.yaml` via
`runbook_url` (rule 8 of the service contract, `docs/service-contract.md`).
All three alerts are generated from `services/demo-api/service.yaml`'s
`slo` block — nothing below is hand-tuned per alert.

## Alerts

demo-api's SLO is `availability: 99.5` over a `30d` window, i.e. an error
budget of `0.005` (0.5%). The two error-budget alerts are Google SRE workbook multiwindow burn-rate alerts (BURN_RATE_FAST = 14.4, BURN_RATE_SLOW = 6.0 in src/platformctl/render.py). A burn rate of 1 means the budget is consumed exactly over the 30d window; a burn rate of 14.4 means it would be gone in ~2 days, and 6.0 in ~5 days. Each alert requires the burn rate to exceed its threshold over both a short and a long window — the short window makes it responsive, the long window suppresses false pages from brief spikes. The constants are independent of the SLO value; only the error budget they multiply changes.

### DemoApiErrorBudgetBurnFast — `severity: page`

```
demo_api:sli_error_ratio:rate5m > (14.4 * 0.005) and demo_api:sli_error_ratio:rate1h > (14.4 * 0.005)
```

5xx rate over both the last 5 minutes and the last hour exceeds 14.4x the
error budget. At this rate the 30d budget is gone in about 2 days. `for: 2m`
— pages fast on purpose. This is almost always a bad deploy, not organic
traffic.

### DemoApiErrorBudgetBurnSlow — `severity: ticket`

```
demo_api:sli_error_ratio:rate30m > (6.0 * 0.005) and demo_api:sli_error_ratio:rate6h > (6.0 * 0.005)
```

Same idea at a slower burn (6x budget over 30m and 6h). At this rate the
budget is gone in about 5 days. `for: 15m`. Files a ticket, doesn't page —
still worth same-day triage.

### DemoApiLatencyP99High — `severity: page`

```
demo_api:sli_latency_p99:seconds > 0.5
```

p99 request latency (from `http_request_duration_seconds_bucket`) has
exceeded the `slo.latency_p99_ms: 500` threshold for 5 minutes straight.

## 1. Confirm impact

Open the generated dashboard (title `demo-api`, uid `b8177311eb1224c6`) in
Grafana:

```
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
open http://localhost:3000/d/b8177311eb1224c6/demo-api
```

Or query Prometheus directly:

```
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
```

Then, at http://localhost:9090/graph:

```promql
# current p99 latency
demo_api:sli_latency_p99:seconds

# 5m / 1h / 30m / 6h error ratios — the exact windows the two burn-rate alerts use
demo_api:sli_error_ratio:rate5m
demo_api:sli_error_ratio:rate1h
demo_api:sli_error_ratio:rate30m
demo_api:sli_error_ratio:rate6h

# remaining 30d error budget (the dashboard's "Error budget remaining" panel)
1 - (demo_api:sli_error_ratio:rate30d / 0.005)
```

Or from `platformctl` (checks ArgoCD sync/health and any currently firing
alert for this service — no port-forward needed):

```
platformctl status demo-api
```

## 2. Identify the offending change

demo-api has no separate chaos tooling — the `/work` endpoint reads
`LATENCY_MS` and `ERROR_RATE` from its own environment on every request
(`examples/demo-api/app.py`), so a bad deploy is always a manifest change
setting one of those too high, or a bad image tag. Find it:

```
git log --oneline -10 -- services/demo-api/service.yaml
git log -p -3 -- services/demo-api/service.yaml
```

Look specifically at `runtime.env` (`LATENCY_MS`, `ERROR_RATE`) and
`image.tag`. Confirm what's actually running:

```
platformctl status demo-api   # image= field
```

Cross-check that tag against the diff — if they match the last commit to
`services/demo-api/service.yaml`, that commit is the change to revert.

## 3. Rollback (gitops-revert)

`operations.rollback: gitops-revert` is the only strategy this platform
supports. There is no manual `kubectl edit` or `kubectl rollout undo` step —
the manifest is the only source of truth, and ArgoCD's `selfHeal: true`
means a hand-edit to the live Deployment would just get reverted back to
whatever's in git anyway.

```
# 1. Revert the offending commit(s) to services/demo-api/service.yaml
#    identified in step 2. If the bad change was folded into a larger
#    commit, revert the whole commit — service.yaml is the only
#    hand-written file in that diff that can be wrong.
git revert --no-edit <bad-commit-sha>

# 2. Regenerate the four derived artifacts from the reverted manifest.
platformctl render demo-api

# 3. Confirm the revert actually restored a valid, matching state — this
#    must produce zero diff in the derived artifacts if step 1 alone was
#    sufficient (render is pure and deterministic).
git status

# 4. Push. ArgoCD's automated sync (argocd/apps/demo-api.yaml) picks this
#    up on its own; no kubectl apply.
git push
```

## 4. Confirm resolution

```
platformctl status demo-api
```

Expect `OK demo-api: sync=Synced health=Healthy ... alerts=none`. If sync
is still `OutOfSync` or `Progressing` after a couple of minutes:

```
kubectl get application demo-api -n argocd -o yaml
```

The error-budget alerts (`for: 2m` / `for: 15m`) and the latency alert
(`for: 5m`) all clear on their own once the underlying `demo_api:sli_*`
series drop back under threshold — no manual alert silencing is needed or
supported on this platform.

## 5. Postmortem

Any page-severity alert (`DemoApiErrorBudgetBurnFast`,
`DemoApiLatencyP99High`) gets a postmortem from
`docs/incidents/TEMPLATE.md`, filed under `docs/incidents/`.
