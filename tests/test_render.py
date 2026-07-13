from platformctl.render import render_grafana_dashboard, render_prometheus_rules
from platformctl.schema import ServiceManifest

from conftest import valid_manifest


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
    assert "checkout-api:sli_error_ratio:rate30d" in window_record_names


def test_dashboard_error_budget_panel_uses_window_scoped_rule() -> None:
    dashboard = render_grafana_dashboard(manifest())
    budget_panel = next(p for p in dashboard["panels"] if p["title"] == "Error budget remaining")
    expr = budget_panel["targets"][0]["expr"]
    assert "checkout-api:sli_error_ratio:rate30d" in expr
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
