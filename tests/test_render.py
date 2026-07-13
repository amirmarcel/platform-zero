import re
from pathlib import Path

from platformctl.render import (
    find_orphaned_artifacts,
    prune_orphaned_artifacts,
    render_grafana_dashboard,
    render_prometheus_rules,
)
from platformctl.schema import ServiceManifest

from conftest import valid_manifest

# Prometheus metric/rule-name grammar: [a-zA-Z_:][a-zA-Z0-9_:]*
_VALID_PROMETHEUS_IDENTIFIER = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")


def manifest(overrides: dict | None = None) -> ServiceManifest:
    data = valid_manifest()
    if overrides:
        data.update(overrides)
    return ServiceManifest.model_validate(data)


def _rules_by_kind(rules: dict) -> tuple[list[dict], list[dict]]:
    all_rules = rules["groups"][0]["rules"]
    recordings = [r for r in all_rules if "record" in r]
    alerts = [r for r in all_rules if "alert" in r]
    return recordings, alerts


# Fix 1: latency SLO must produce its own alert, not just availability


def test_latency_alert_is_generated() -> None:
    _, alerts = _rules_by_kind(render_prometheus_rules(manifest()))
    latency_alerts = [a for a in alerts if "Latency" in a["alert"]]
    assert len(latency_alerts) == 1

    alert = latency_alerts[0]
    assert "sli_latency_p99:seconds > 0.3" in alert["expr"]  # 300ms -> 0.3s
    assert alert["for"]
    assert alert["annotations"]["runbook_url"] == "docs/runbooks/checkout-api.md"
    assert alert["annotations"]["owner"] == "payments-team"


def test_latency_alert_threshold_tracks_slo_field() -> None:
    m = manifest()
    m.slo.latency_p99_ms = 750
    _, alerts = _rules_by_kind(render_prometheus_rules(m))
    latency_alert = next(a for a in alerts if "Latency" in a["alert"])
    assert "> 0.75" in latency_alert["expr"]


# Fix 2: error budget remaining must use a window-scoped recording rule, not a burn rate


def test_window_scoped_recording_rule_exists() -> None:
    recordings, _ = _rules_by_kind(render_prometheus_rules(manifest()))
    window_record_names = {r["record"] for r in recordings}
    assert "checkout_api:sli_error_ratio:rate30d" in window_record_names


def test_dashboard_error_budget_panel_uses_window_scoped_rule() -> None:
    dashboard = render_grafana_dashboard(manifest())
    budget_panel = next(p for p in dashboard["panels"] if p["title"] == "Error budget remaining")
    expr = budget_panel["targets"][0]["expr"]
    assert "checkout_api:sli_error_ratio:rate30d" in expr
    assert "rate1h" not in expr


# Fix 3: saturation panel must select on container/namespace, not job (cAdvisor has no job label)


def test_saturation_panel_uses_container_and_namespace_selectors() -> None:
    dashboard = render_grafana_dashboard(manifest())
    saturation_panel = next(p for p in dashboard["panels"] if "Saturation" in p["title"])
    exprs = [t["expr"] for t in saturation_panel["targets"]]
    for expr in exprs:
        assert 'container="checkout-api"' in expr
        assert 'namespace="checkout-api"' in expr
        assert 'job="checkout-api"' not in expr


# Fix 4: a hyphenated service name must not leak into recording-rule or alert
# names — Prometheus metric names must match [a-zA-Z_:][a-zA-Z0-9_:]*, and the
# Prometheus Operator's validating webhook rejects a PrometheusRule that
# doesn't. Labels, selectors, group names, and summaries may keep the raw
# hyphenated name; only identifiers derived from it may not.


def test_recording_and_alert_names_are_valid_prometheus_identifiers() -> None:
    m = manifest({"name": "demo-api"})
    recordings, alerts = _rules_by_kind(render_prometheus_rules(m))

    for rule in recordings:
        assert _VALID_PROMETHEUS_IDENTIFIER.match(rule["record"]), rule["record"]
    for rule in alerts:
        assert _VALID_PROMETHEUS_IDENTIFIER.match(rule["alert"]), rule["alert"]


def test_alert_expressions_reference_sanitized_recording_rule_names() -> None:
    m = manifest({"name": "demo-api"})
    _, alerts = _rules_by_kind(render_prometheus_rules(m))

    for rule in alerts:
        assert "demo-api:" not in rule["expr"], rule["expr"]
        assert "demo_api:" in rule["expr"], rule["expr"]


def test_job_selector_and_group_name_keep_the_raw_hyphenated_name() -> None:
    m = manifest({"name": "demo-api"})
    rules = render_prometheus_rules(m)

    assert rules["groups"][0]["name"] == "demo-api.rules"
    recordings, _ = _rules_by_kind(rules)
    assert 'job="demo-api"' in recordings[0]["expr"]


# Orphaned artifacts: a derived artifact with no corresponding service must
# be detected (and, on request, pruned) — see docs/service-contract.md rule 10.


def _write(path: Path, content: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_find_orphaned_artifacts_empty_when_all_artifacts_have_a_service(tmp_path: Path) -> None:
    _write(tmp_path / "helm" / "service" / "values" / "checkout-api.yaml")
    _write(tmp_path / "argocd" / "apps" / "checkout-api.yaml")
    _write(tmp_path / "observability" / "rules" / "checkout-api.yaml")
    _write(tmp_path / "observability" / "dashboards" / "checkout-api.json")

    assert find_orphaned_artifacts(tmp_path, {"checkout-api"}) == []


def test_find_orphaned_artifacts_detects_all_four_kinds_for_a_deleted_service(tmp_path: Path) -> None:
    _write(tmp_path / "helm" / "service" / "values" / "checkout-api.yaml")
    _write(tmp_path / "argocd" / "apps" / "checkout-api.yaml")
    _write(tmp_path / "observability" / "rules" / "checkout-api.yaml")
    _write(tmp_path / "observability" / "dashboards" / "checkout-api.json")

    orphaned = find_orphaned_artifacts(tmp_path, service_names=set())

    assert set(orphaned) == {
        "helm/service/values/checkout-api.yaml",
        "argocd/apps/checkout-api.yaml",
        "observability/rules/checkout-api.yaml",
        "observability/dashboards/checkout-api.json",
    }


def test_find_orphaned_artifacts_ignores_observability_application(tmp_path: Path) -> None:
    _write(tmp_path / "argocd" / "apps" / "observability.yaml")

    assert find_orphaned_artifacts(tmp_path, service_names=set()) == []


def test_find_orphaned_artifacts_leaves_artifacts_for_surviving_services_alone(tmp_path: Path) -> None:
    _write(tmp_path / "helm" / "service" / "values" / "checkout-api.yaml")
    _write(tmp_path / "helm" / "service" / "values" / "billing-worker.yaml")

    orphaned = find_orphaned_artifacts(tmp_path, service_names={"checkout-api"})

    assert orphaned == ["helm/service/values/billing-worker.yaml"]


def test_prune_orphaned_artifacts_deletes_them_and_returns_their_paths(tmp_path: Path) -> None:
    _write(tmp_path / "helm" / "service" / "values" / "checkout-api.yaml")
    _write(tmp_path / "argocd" / "apps" / "checkout-api.yaml")

    removed = prune_orphaned_artifacts(tmp_path, service_names=set())

    assert set(removed) == {"helm/service/values/checkout-api.yaml", "argocd/apps/checkout-api.yaml"}
    assert not (tmp_path / "helm" / "service" / "values" / "checkout-api.yaml").exists()
    assert not (tmp_path / "argocd" / "apps" / "checkout-api.yaml").exists()


def test_prune_orphaned_artifacts_does_not_touch_files_for_existing_services(tmp_path: Path) -> None:
    kept = tmp_path / "helm" / "service" / "values" / "checkout-api.yaml"
    _write(kept)

    removed = prune_orphaned_artifacts(tmp_path, service_names={"checkout-api"})

    assert removed == []
    assert kept.exists()
