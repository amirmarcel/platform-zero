"""platformctl status — reports, for a live service, exactly what the
service contract (docs/service-contract.md) promised on merge: ArgoCD sync
and health, the image tag actually running, and whether any Prometheus
alert tied to this service is currently firing.

The cluster I/O (cluster.py) is kept separate from `evaluate_status` below
so the decision logic can be unit-tested against fixture JSON with no
cluster required.
"""

from dataclasses import dataclass, field

from platformctl.cluster import KubectlNotFoundError, kubectl_get_json
from platformctl.render import _alert_name
from platformctl.schema import ServiceManifest

ARGOCD_NAMESPACE = "argocd"

# Matches the Helm release name `make platform-install` (Makefile) installs
# kube-prometheus-stack under, and the port-forward target documented in
# docs/local-setup.md. `kubectl get --raw .../proxy/...` reaches it through
# the API server without needing a running port-forward.
MONITORING_NAMESPACE = "monitoring"
PROMETHEUS_SERVICE = "kube-prometheus-stack-prometheus"
PROMETHEUS_PORT = 9090

HEALTHY_STATUS = "Healthy"
SYNCED_STATUS = "Synced"

# Reported when the ArgoCD Application doesn't exist yet — the normal state
# between `platformctl render` and the first merge to main, not a failure.
NOT_DEPLOYED_STATUS = "NotDeployed"


@dataclass
class ServiceStatus:
    name: str
    sync_status: str
    health_status: str
    image_tag: str
    firing_alerts: list[str] = field(default_factory=list)
    deployed: bool = True

    @property
    def healthy(self) -> bool:
        return (
            self.deployed
            and self.sync_status == SYNCED_STATUS
            and self.health_status == HEALTHY_STATUS
            and not self.firing_alerts
        )


def fetch_application(name: str) -> dict:
    """The ArgoCD Application `platformctl render` generated for this
    service — its .status carries sync, health, and the live image list."""
    return kubectl_get_json(["get", "application", name, "-n", ARGOCD_NAMESPACE, "-o", "json"])


def fetch_active_alerts() -> list[dict]:
    """Every currently active (pending or firing) alert known to
    kube-prometheus-stack's Prometheus, reached via the API server proxy —
    no port-forward required."""
    path = (
        f"/api/v1/namespaces/{MONITORING_NAMESPACE}/services/"
        f"{PROMETHEUS_SERVICE}:{PROMETHEUS_PORT}/proxy/api/v1/alerts"
    )
    response = kubectl_get_json(["get", "--raw", path])
    return response.get("data", {}).get("alerts", [])


def evaluate_status(manifest: ServiceManifest, application: dict, alerts: list[dict]) -> ServiceStatus:
    """Pure decision logic — no I/O. Fed live JSON in production, fixture
    JSON in tests."""
    status = application.get("status", {})
    sync_status = status.get("sync", {}).get("status", "Unknown")
    health_status = status.get("health", {}).get("status", "Unknown")

    image_tag = "unknown"
    for image in status.get("summary", {}).get("images", []):
        repository, _, tag = image.rpartition(":")
        if repository == manifest.image.repository:
            image_tag = tag
            break

    # Alerts carry no service-identifying label of their own (the
    # recording-rule exprs are `sum(...)` with no `by (...)`, so job/service
    # labels are aggregated away) — the alert *name* is the only link back
    # to a service, via the same `_alert_name` CamelCase prefix render.py
    # uses to generate it (e.g. "demo-api" -> "DemoApi*").
    prefix = _alert_name(manifest.name)
    firing_alerts = sorted(
        {
            alert["labels"]["alertname"]
            for alert in alerts
            if alert.get("state") == "firing" and alert.get("labels", {}).get("alertname", "").startswith(prefix)
        }
    )

    return ServiceStatus(
        name=manifest.name,
        sync_status=sync_status,
        health_status=health_status,
        image_tag=image_tag,
        firing_alerts=firing_alerts,
    )


def get_service_status(manifest: ServiceManifest, alerts: list[dict]) -> ServiceStatus:
    """Fetch this service's Application from the cluster and evaluate its
    status against the already-fetched alert list.

    Rendered-but-not-yet-deployed is a normal state — exactly where a
    developer sits between `render` and the first merge to main — so a
    missing Application is not an error here: it comes back as a
    ServiceStatus with deployed=False. Raises KubectlError for a genuine
    cluster failure (no kubectl on PATH, an auth error, a timeout, ...).
    """
    try:
        application = fetch_application(manifest.name)
    except KubectlNotFoundError:
        return ServiceStatus(
            name=manifest.name,
            sync_status=NOT_DEPLOYED_STATUS,
            health_status=NOT_DEPLOYED_STATUS,
            image_tag="unknown",
            firing_alerts=[],
            deployed=False,
        )
    return evaluate_status(manifest, application, alerts)
