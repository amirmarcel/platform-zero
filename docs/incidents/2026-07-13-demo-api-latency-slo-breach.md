# Incident: demo-api p99 latency SLO breach

- **Service:** demo-api (tier 2, owned by platform-team) (`services/demo-api/service.yaml`)
- **Severity:** page (`DemoApiLatencyP99High`)
- **Status:** Resolved
- **Date:** 2026-07-13
- **Author(s):**

## Summary

A configuration change to `services/demo-api/service.yaml` set `LATENCY_MS` to
`600`, above the service's own declared SLO of `latency_p99_ms: 500`. The change
passed every gate in the platform's validation chain — schema validation, drift
check, `promtool`, `kubeconform`, and the full unit test suite — because the
manifest was *well-formed*. It was simply wrong.

The bad config reached production through the normal golden path: commit → render
→ ArgoCD sync → running pods. `platformctl status` flagged the service as
degraded 5 minutes after traffic resumed, 18 seconds ahead of the
`DemoApiLatencyP99High` SLO alert's own confirmed transition to FIRING — that
alert was generated from the same manifest that broke it. Resolution was a
GitOps revert. See Timeline and Detection for the full breakdown, including the
load-generator outage that delayed all of the above.

## Impact

- **Duration of degradation:** ~19 minutes (11:53 – 12:12)
- **p99 latency:** 748ms observed, against a 500ms SLO — a ~150x increase over the
  pre-incident baseline of ~5ms
- **Availability SLO:** unaffected. `ERROR_RATE` remained `0.0`; the service
  returned correct responses, only slowly. The 30d error budget was not consumed.
- **Blast radius:** limited to demo-api. No dependent services.

## Timeline

| Time (EDT) | Event | Elapsed |
|---|---|---|
| 11:51:01 | `LATENCY_MS: "600"` committed and pushed. CI passes. | T0 |
| 11:53:16 | ArgoCD syncs; pods roll with the bad config. Degradation begins. | +2m15s |
| 11:51–11:59 | **Traffic generator failing silently.** No requests reaching the service; no signal. | — |
| 11:59 | Traffic restored. p99 begins climbing. | +8m |
| 12:04:07 | `platformctl status` reports `DEGRADED`, naming the alert. | +13m |
| 12:04:25 | `DemoApiLatencyP99High` transitions to FIRING in Prometheus — confirmed from the `ALERTS{alertname="DemoApiLatencyP99High"}` series (2026-07-13T16:04:25Z). | +13m24s |
| ~12:06 | Responder manually observes FIRING state via a Prometheus UI browser refresh — human observation latency, not the actual transition time (see Detection). | +15m |
| 12:10:17 | **Mitigation begins.** `git revert` of the offending commit. | +19m |
| 12:11:53 | ArgoCD syncs the revert; pods roll. | +21m |
| 12:12:24 | **Service recovered.** `LATENCY_MS=0` live; p99 back to sub-millisecond. | +21m |
| 12:17:04 | Alert clears. | +26m |

**Template-defined metrics** (`docs/incidents/TEMPLATE.md`'s fixed
definitions, for cross-incident comparability):

- **Time to detect** (change merged/deployed → alert fires): ~13 minutes
  from commit (11:51:01 → 12:04:25), or ~11 minutes from when the bad pods
  actually rolled (11:53:16 → 12:04:25) — see the confound below before
  reading either number as "how fast the alert responded to a real signal."
- **Time to mitigate** (alert fires → mitigation pushed): 6 minutes
  (12:04:25 → 12:10:17).
- **Time to resolve** (alert fires → alert clears): 13 minutes
  (12:04:25 → 12:17:04).

**Confound:** the load generator was silently hitting a dead port-forward
from 11:51 to 11:59, so there was no real traffic — and therefore no
latency signal — for roughly the first 8 minutes of the "time to detect"
window above. That inflates the template metric independent of how well
the alert performed once real signal existed. Measured from when traffic
actually resumed instead: the alert fired 5 minutes later (11:59 →
12:04:25) — essentially exactly the alert's `for: 5m` clause, with no
additional delay. (The `demo_api:sli_latency_p99:seconds` recording rule's
own `[5m]` rate window doesn't need to fill before reflecting elevated
latency — a fixed per-request delay like `LATENCY_MS` shows up in the p99
almost immediately once slow requests start landing — so the `for: 5m`
clause accounts for essentially the entire 5m25s.) `platformctl status`
reported `DEGRADED` 18 seconds before the confirmed transition (11:59 →
12:04:07) — one polling interval ahead, not a discrepancy.

**Supplementary metrics:**

- **Time to recover** (mitigation pushed → service healthy): 2 minutes
  (12:10:17 → 12:12:24).
- **Alert lag after recovery** (service healthy → alert clears): ~5 minutes
  (12:12:24 → 12:17:04) — inherent to the 5m rate window plus `for: 5m` on
  `DemoApiLatencyP99High`, not a response-time metric.

## Root cause

I set LATENCY_MS to "600" in services/demo-api/service.yaml. The service sleeps that long on every /work request. The same file declares slo.latency_p99_ms: 500. The manifest promised 500ms and configured 600ms, and nothing in the platform noticed the contradiction.

Every gate passed, and each was correct to pass. platformctl validate checks the contract's ten rules (owner, immutable tag, resource bounds, runbook existence, name grammar, SLO bounds) and "600" violates none of them; it's a valid string in a valid env entry. The drift check passed because the renderer faithfully rendered what it was given. promtool and kubeconform passed because the generated rules and manifests were structurally sound. All 100 unit tests passed because nothing in the platform was broken. The configuration was well-formed. It was just wrong.

No additional validation rule would have caught this in the general case. LATENCY_MS is legible only because this is a demo service whose knobs the platform happens to understand. A real service's CACHE_TTL, POOL_SIZE, or MAX_WORKERS are opaque strings, and the platform has no way to reason about what changing one of them does to latency, throughput, or an SLO. The failure is semantic; every gate upstream of deployment is syntactic.

What caught it was the SLO: DemoApiLatencyP99High, generated from slo.latency_p99_ms: 500 in the same manifest that contained the bad value. Nothing else did. ArgoCD reported Synced / Healthy throughout, because the desired state was deployed and the probes passed. platformctl status reported image=v0.1.0 throughout, because the image never changed. Three systems all correctly reporting "fine" while the service was running 150x over its latency budget. Static validation proves a deployment is well-formed; only production, measured against a declared objective, proves it is correct.

## How it was fixed

`git revert` of the offending commit, followed by `platformctl render demo-api`.

The re-render produced **zero diff** — `git status` reported a clean working tree.
Because rendering is pure and byte-deterministic, reverting the manifest was
sufficient to restore every derived artifact exactly; no manual repair of Helm
values, ArgoCD Applications, Prometheus rules, or dashboards was needed.

ArgoCD picked up the revert and rolled the pods without any `kubectl` intervention.

## Detection

What caught it: `DemoApiLatencyP99High`, the SLO alert generated from the same
`services/demo-api/service.yaml` manifest that caused the regression. Its
confirmed FIRING transition, from `ALERTS{alertname="DemoApiLatencyP99High"}`,
is 12:04:25 (2026-07-13T16:04:25Z). `platformctl status` reported `DEGRADED`
(naming the alert) 18 seconds earlier, at 12:04:07 — one polling interval
ahead of the confirmed transition, consistent with normal polling cadence.

I did not notice the degradation myself until I refreshed the Prometheus UI at ~12:06, 
roughly 90 seconds after platformctl status had already reported it. 
The 18-second figure is the meaningful one (the CLI's polling cadence against the alert's 
actual transition); the 90 seconds is a measure of my browser habits, not of the tooling. 
The point stands either way: a scriptable one-command check surfaced the degradation 
without anyone needing to be watching a dashboard.

What did not catch it:

- **CI**, at commit time — `platformctl validate`, `platformctl render --check`,
  `promtool check rules`, `kubeconform`, and all 100 unit tests passed (see Root
  cause). None of these gates evaluates runtime behavior against the SLO.
- **ArgoCD health**, throughout the degradation — `sync=Synced health=Healthy`
  the entire time. The desired state was deployed and the pods were running,
  which is a different question from whether the service was meeting its SLO.
- **`platformctl status`'s `image=` field**, throughout — it read `v0.1.0` before,
  during, and after the incident, because the regression was a `runtime.env`
  change, not an image change. The image tag was never the signal here.

Detection was also delayed independently of all of the above: the traffic
generator (`scripts/load.sh`) was hitting a dead port-forward from 11:51 to
11:59 and reported requests as issued without checking any response, so no
real traffic reached the service and no latency signal existed for the alert
to evaluate. Real traffic only resumed at 11:59 (+8m); the alert fired 5
minutes after that (12:04:25), consistent with the alert's own `for: 5m`
clause and no more — see the Timeline confound note for why the recording
rule's `[5m]` window didn't add further delay on top of that.

The error-rate and error-budget panels are empty by design. The failure was purely 
latency: ERROR_RATE remained 0.0 throughout, so the service returned correct responses 
and there are no 5xx to plot. The error-budget panel divides by a 30-day error-ratio 
recording rule, and a kind cluster that has existed for a few hours has no 30 days of 
history — the query is correct for a real deployment and cannot populate here.

![demo-api dashboard during the incident](../images/incident-dashboard.png)

## What went well

- **The SLO alert did its job.** The one signal that caught this was the one derived
  from the service's own declared objective.
- **The rollback was mechanical.** `revert → render → push`, zero diff, no manual
  repair. The determinism guarantee held under pressure.
- **`platformctl status` gave a single-command answer.** It reported `DEGRADED` with
  the alert named, two minutes before the operator would have thought to check
  Prometheus.
- **No `kubectl` was used to fix production.** The GitOps loop handled the rollback
  end to end, as the contract promises.

## What didn't go well

- **The observability tooling failed silently and nobody noticed for 8 minutes.**
  The load generator printed "600 requests issued so far" while every single request
  was hitting a dead port-forward. A tool that reports success without checking its
  responses is worse than no tool: it manufactures false confidence. This is the
  most serious finding here — it delayed detection by 8 minutes in a controlled
  exercise, and would have done the same in a real incident.

- **`platformctl status` reported `image=v0.1.0` throughout the incident.** The image
  tag never changed; only an environment variable did. A status tool that tracks
  image tags is blind to config-only regressions — which are a large fraction of real
  incidents.

- **ArgoCD reported `sync=Synced health=Healthy` for the entire degradation.** From
  the deployment system's perspective, nothing was wrong: the desired state was
  deployed, the pods were running, the probes passed. This is correct behavior and
  also precisely why health checks are not a substitute for SLOs.

- **The alert fired for ~5 minutes after the service had fully recovered.** This is
  inherent to a 5-minute rate window plus a `for: 5m` clause, not a bug — but an
  on-call engineer who doesn't understand it will keep pulling levers on an
  already-healthy system. It isn't documented anywhere they'd look.

## Action items

| # | Action | Owner | Priority | Status |
|---|---|---|---|---|
| 1 | `scripts/load.sh` must validate responses — assert HTTP 200 and non-empty body, and fail loudly on connection errors rather than counting them as issued requests. | platform-team | High | not started |
| 2 | `platformctl status` should surface the deployed manifest's config hash, not just the image tag, so config-only changes are visible. | platform-team | High | not started |
| 3 | Document the alert-clear lag in `docs/runbooks/demo-api.md` — explicitly state that recovery precedes alert resolution by roughly one rate window, and that a cleared p99 with a still-firing alert means "wait," not "escalate." | platform-team | Medium | not started |
| 4 | Consider a `platformctl validate` rule that flags manifests whose `runtime.env` contains platform-recognized latency/error knobs exceeding the declared SLO. Narrow in scope and only works for known keys — but this specific footgun is cheap to close. | platform-team | Low | not started |