"""demo-api — the reference service for platform-zero's GitOps loop.

Exposes the two probes and the two metrics every service.yaml on this
platform is required to have an SLO and dashboard generated from:
http_requests_total and http_request_duration_seconds.
"""

import os
import random
import time

from flask import Flask, Response, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = Flask(__name__)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)


def _route_label() -> str:
    """The matched route rule, not the raw path — request.path is unbounded
    cardinality (every 404 on a random path would mint a new series)."""
    if request.url_rule is not None:
        return request.url_rule.rule
    return "<unmatched>"


@app.before_request
def _start_timer() -> None:
    request.environ["start_time"] = time.perf_counter()


@app.after_request
def _record_metrics(response: Response) -> Response:
    duration = time.perf_counter() - request.environ["start_time"]
    route = _route_label()
    REQUEST_LATENCY.labels(request.method, route).observe(duration)
    REQUEST_COUNT.labels(request.method, route, response.status_code).inc()
    return response


@app.get("/healthz/ready")
def ready() -> tuple[dict, int]:
    return {"status": "ready"}, 200


@app.get("/healthz/live")
def live() -> tuple[dict, int]:
    return {"status": "alive"}, 200


@app.get("/")
def index() -> tuple[dict, int]:
    return {"service": "demo-api", "status": "ok"}, 200


@app.get("/work")
def work() -> tuple[dict, int]:
    """Incident-injection endpoint. LATENCY_MS and ERROR_RATE are read from
    the environment on every request, so a bad deploy is a manifest with a
    bad env value, and a rollback is reverting that commit — no separate
    chaos tooling.
    """
    latency_ms = float(os.environ.get("LATENCY_MS", "0"))
    if latency_ms > 0:
        time.sleep(latency_ms / 1000)

    error_rate = float(os.environ.get("ERROR_RATE", "0.0"))
    if random.random() < error_rate:
        return {"status": "error"}, 500

    return {"status": "ok"}, 200


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
