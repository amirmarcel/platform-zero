"""platformctl render — derives the four artifacts in docs/service-contract.md
from a validated service.yaml. Rendering is pure and byte-deterministic: same
manifest in, byte-identical artifacts out. No timestamps, no random IDs.
"""

import hashlib
import json
import re
from pathlib import Path

import yaml

from platformctl.quantities import parse_cpu, parse_memory
from platformctl.schema import ServiceManifest

# Google SRE workbook multiwindow multi-burn-rate constants: a fast-burn
# alert pages if the 30d budget would be exhausted in ~2 days, a slow-burn
# alert tickets if it would be exhausted in ~5 days. Independent of the
# specific SLO value — they scale with the error budget fraction.
BURN_RATE_FAST = 14.4
BURN_RATE_SLOW = 6.0


def artifact_paths(name: str) -> dict[str, str]:
    """Relative (POSIX) paths of the four derived artifacts for a service."""
    return {
        "helm_values": f"helm/service/values/{name}.yaml",
        "argocd_app": f"argocd/apps/{name}.yaml",
        "prometheus_rules": f"observability/rules/{name}.yaml",
        "grafana_dashboard": f"observability/dashboards/{name}.json",
    }


def dashboard_uid(name: str) -> str:
    """Stable dashboard uid derived from the service name — never generated."""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


def _window_suffix(window: str) -> str:
    """Sanitize slo.window (e.g. '30d') into a valid Prometheus metric-name suffix."""
    return re.sub(r"[^0-9A-Za-z]", "_", window)


def render_helm_values(manifest: ServiceManifest) -> dict:
    return {
        "name": manifest.name,
        "owner": manifest.owner,
        "tier": manifest.tier,
        "image": {
            "repository": manifest.image.repository,
            "tag": manifest.image.tag,
        },
        "runtime": {
            "port": manifest.runtime.port,
            "replicas": manifest.runtime.replicas,
            "resources": {
                "requests": {
                    "cpu": manifest.runtime.resources.requests.cpu,
                    "memory": manifest.runtime.resources.requests.memory,
                },
                "limits": {
                    "cpu": manifest.runtime.resources.limits.cpu,
                    "memory": manifest.runtime.resources.limits.memory,
                },
            },
            "probes": {
                "readiness": manifest.runtime.probes.readiness,
                "liveness": manifest.runtime.probes.liveness,
            },
        },
    }


def render_argocd_application(manifest: ServiceManifest, repo_url: str) -> dict:
    return {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {
            "name": manifest.name,
            "namespace": "argocd",
            "labels": {
                "platform.io/owner": manifest.owner,
                "platform.io/tier": str(manifest.tier),
            },
        },
        "spec": {
            "project": "default",
            "source": {
                "repoURL": repo_url,
                "targetRevision": "HEAD",
                "path": "helm/service",
                "helm": {
                    "valueFiles": [f"values/{manifest.name}.yaml"],
                },
            },
            "destination": {
                "server": "https://kubernetes.default.svc",
                "namespace": manifest.name,
            },
            "syncPolicy": {
                "automated": {
                    "prune": True,
                    "selfHeal": True,
                },
            },
        },
    }


def _error_budget(manifest: ServiceManifest) -> float:
    return round((100 - manifest.slo.availability) / 100, 6)


def render_prometheus_rules(manifest: ServiceManifest) -> dict:
    name = manifest.name
    job_selector = f'job="{name}"'
    error_budget = _error_budget(manifest)
    window = manifest.slo.window
    window_record = f"{name}:sli_error_ratio:rate{_window_suffix(window)}"
    latency_threshold_seconds = manifest.slo.latency_p99_ms / 1000

    def error_ratio_expr(window_arg: str) -> str:
        return (
            f'sum(rate(http_requests_total{{{job_selector},code=~"5.."}}[{window_arg}])) / '
            f'sum(rate(http_requests_total{{{job_selector}}}[{window_arg}]))'
        )

    recording_rules = [
        {"record": f"{name}:sli_error_ratio:rate5m", "expr": error_ratio_expr("5m")},
        {"record": f"{name}:sli_error_ratio:rate30m", "expr": error_ratio_expr("30m")},
        {"record": f"{name}:sli_error_ratio:rate1h", "expr": error_ratio_expr("1h")},
        {"record": f"{name}:sli_error_ratio:rate6h", "expr": error_ratio_expr("6h")},
        # Error ratio over the full SLO window — used to compute budget remaining,
        # as opposed to the short windows above which are burn-rate inputs.
        {"record": window_record, "expr": error_ratio_expr(window)},
        {
            "record": f"{name}:sli_latency_p99:seconds",
            "expr": (
                "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket"
                f"{{{job_selector}}}[5m])) by (le))"
            ),
        },
    ]

    common_labels = {"owner": manifest.owner, "tier": str(manifest.tier)}
    common_annotations = {
        "runbook_url": manifest.operations.runbook,
        "owner": manifest.owner,
    }

    alert_rules = [
        {
            "alert": f"{name}ErrorBudgetBurnFast",
            "expr": (
                f"{name}:sli_error_ratio:rate5m > ({BURN_RATE_FAST} * {error_budget}) "
                f"and {name}:sli_error_ratio:rate1h > ({BURN_RATE_FAST} * {error_budget})"
            ),
            "for": "2m",
            "labels": {**common_labels, "severity": "page"},
            "annotations": {
                **common_annotations,
                "summary": (
                    f"{name} is burning its {window} error budget fast "
                    f"(availability SLO {manifest.slo.availability}%)"
                ),
            },
        },
        {
            "alert": f"{name}ErrorBudgetBurnSlow",
            "expr": (
                f"{name}:sli_error_ratio:rate30m > ({BURN_RATE_SLOW} * {error_budget}) "
                f"and {name}:sli_error_ratio:rate6h > ({BURN_RATE_SLOW} * {error_budget})"
            ),
            "for": "15m",
            "labels": {**common_labels, "severity": "ticket"},
            "annotations": {
                **common_annotations,
                "summary": (
                    f"{name} is burning its {window} error budget slowly "
                    f"(availability SLO {manifest.slo.availability}%)"
                ),
            },
        },
        {
            "alert": f"{name}LatencyP99High",
            "expr": f"{name}:sli_latency_p99:seconds > {latency_threshold_seconds}",
            "for": "5m",
            "labels": {**common_labels, "severity": "page"},
            "annotations": {
                **common_annotations,
                "summary": (
                    f"{name} p99 latency exceeds its SLO threshold of "
                    f"{manifest.slo.latency_p99_ms}ms"
                ),
            },
        },
    ]

    return {
        "groups": [
            {
                "name": f"{name}.rules",
                "rules": recording_rules + alert_rules,
            }
        ]
    }


def render_grafana_dashboard(manifest: ServiceManifest) -> dict:
    name = manifest.name
    cadvisor_selector = f'container="{name}",namespace="{name}"'
    cpu_limit_cores = parse_cpu(manifest.runtime.resources.limits.cpu)
    memory_limit_bytes = parse_memory(manifest.runtime.resources.limits.memory)
    window_record = f"{name}:sli_error_ratio:rate{_window_suffix(manifest.slo.window)}"
    error_budget = _error_budget(manifest)

    panels = [
        {
            "id": 1,
            "title": "Latency (p99)",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
            "fieldConfig": {"defaults": {"unit": "s"}},
            "targets": [
                {"expr": f"{name}:sli_latency_p99:seconds", "legendFormat": "p99"}
            ],
        },
        {
            "id": 2,
            "title": "Error rate",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
            "fieldConfig": {"defaults": {"unit": "percentunit"}},
            "targets": [
                {"expr": f"{name}:sli_error_ratio:rate5m", "legendFormat": "5m error ratio"}
            ],
        },
        {
            "id": 3,
            "title": "Saturation (cpu / memory vs limits)",
            "type": "timeseries",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
            "fieldConfig": {"defaults": {"unit": "percentunit"}},
            "targets": [
                {
                    "expr": (
                        f"sum(rate(container_cpu_usage_seconds_total{{{cadvisor_selector}}}[5m])) "
                        f"/ {cpu_limit_cores}"
                    ),
                    "legendFormat": "cpu saturation",
                },
                {
                    "expr": (
                        f"sum(container_memory_working_set_bytes{{{cadvisor_selector}}}) "
                        f"/ {memory_limit_bytes}"
                    ),
                    "legendFormat": "memory saturation",
                },
            ],
        },
        {
            "id": 4,
            "title": "Error budget remaining",
            "type": "stat",
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
            "fieldConfig": {"defaults": {"unit": "percentunit"}},
            "targets": [
                {
                    "expr": f"1 - ({window_record} / {error_budget})",
                    "legendFormat": "budget remaining",
                }
            ],
        },
    ]

    return {
        "annotations": {"list": []},
        "editable": False,
        "panels": panels,
        "schemaVersion": 39,
        "tags": ["platform-zero", f"tier-{manifest.tier}", f"owner-{manifest.owner}"],
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
        "timezone": "utc",
        "title": name,
        "uid": dashboard_uid(name),
        "version": 1,
    }


def _to_yaml_bytes(data: dict) -> bytes:
    return yaml.safe_dump(data, sort_keys=True, default_flow_style=False).encode("utf-8")


def _to_json_bytes(data: dict) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")


def render_artifacts(manifest: ServiceManifest, repo_url: str) -> dict[str, bytes]:
    """Render the four derived artifacts for one service. Pure: no I/O."""
    paths = artifact_paths(manifest.name)
    return {
        paths["helm_values"]: _to_yaml_bytes(render_helm_values(manifest)),
        paths["argocd_app"]: _to_yaml_bytes(render_argocd_application(manifest, repo_url)),
        paths["prometheus_rules"]: _to_yaml_bytes(render_prometheus_rules(manifest)),
        paths["grafana_dashboard"]: _to_json_bytes(render_grafana_dashboard(manifest)),
    }


def write_artifacts(root: Path, artifacts: dict[str, bytes]) -> list[Path]:
    written = []
    for rel_path, content in artifacts.items():
        full_path = root / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        written.append(full_path)
    return written


def check_drift(root: Path, artifacts: dict[str, bytes]) -> list[str]:
    """Rule 10: derived artifacts must match what the manifest implies."""
    drifted = []
    for rel_path, content in artifacts.items():
        full_path = root / rel_path
        if not full_path.is_file():
            drifted.append(f"{rel_path}: missing")
        elif full_path.read_bytes() != content:
            drifted.append(f"{rel_path}: out of date")
    return drifted
