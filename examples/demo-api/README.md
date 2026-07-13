# demo-api

The reference service for platform-zero's GitOps loop. A minimal Flask app
with nothing platform-specific hard-coded into it — everything that makes it
"a platform-zero service" (probes, resources, SLO, dashboard, alerts) comes
from `services/demo-api/service.yaml`, not from this code.

Endpoints:

- `GET /healthz/ready`, `GET /healthz/live` — the probes `service.yaml` declares.
- `GET /metrics` — Prometheus text exposition: `http_requests_total` and
  `http_request_duration_seconds`, labeled by the matched route rule (not the
  raw path, which would be unbounded cardinality).
- `GET /work` — reads `LATENCY_MS` and `ERROR_RATE` from the environment on
  every request and sleeps / fails accordingly. This is the incident-injection
  endpoint: a bad deploy is a manifest that sets a bad env value, and the
  rollback is reverting that commit.
- `GET /` — a trivial endpoint to generate traffic against.

## Run locally

```
pip install -r requirements.txt
python app.py
curl localhost:8080/healthz/ready
curl localhost:8080/metrics
LATENCY_MS=500 ERROR_RATE=0.2 python app.py   # then hit /work
```

## Image

Built and published to `ghcr.io/<owner>/demo-api` by
`.github/workflows/demo-api-image.yaml` on push to `main` (tagged by commit
sha) and on `demo-api-v*` tags (tagged by the matching semver, e.g.
`demo-api-v0.1.0` -> image tag `v0.1.0`). `services/demo-api/service.yaml`
pins to one of those real, published tags — `platformctl validate` rejects
anything else.
