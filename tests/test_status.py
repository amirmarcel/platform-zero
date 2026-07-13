from unittest.mock import patch

import pytest

from platformctl.cluster import KubectlError, KubectlNotFoundError
from platformctl.schema import ServiceManifest
from platformctl.status import ServiceStatus, evaluate_status, get_service_status

from conftest import valid_manifest


def manifest() -> ServiceManifest:
    return ServiceManifest.model_validate(valid_manifest())


def healthy_application(image: str = "ghcr.io/example/checkout-api:v1.4.2") -> dict:
    return {
        "status": {
            "sync": {"status": "Synced"},
            "health": {"status": "Healthy"},
            "summary": {"images": [image]},
        }
    }


def test_healthy_service_with_no_alerts_is_healthy() -> None:
    result = evaluate_status(manifest(), healthy_application(), alerts=[])
    assert result.healthy
    assert result.sync_status == "Synced"
    assert result.health_status == "Healthy"
    assert result.image_tag == "v1.4.2"
    assert result.firing_alerts == []


def test_out_of_sync_is_not_healthy() -> None:
    app = healthy_application()
    app["status"]["sync"]["status"] = "OutOfSync"
    result = evaluate_status(manifest(), app, alerts=[])
    assert not result.healthy
    assert result.sync_status == "OutOfSync"


def test_degraded_health_is_not_healthy() -> None:
    app = healthy_application()
    app["status"]["health"]["status"] = "Degraded"
    result = evaluate_status(manifest(), app, alerts=[])
    assert not result.healthy
    assert result.health_status == "Degraded"


def test_missing_status_fields_report_unknown() -> None:
    result = evaluate_status(manifest(), application={}, alerts=[])
    assert result.sync_status == "Unknown"
    assert result.health_status == "Unknown"
    assert result.image_tag == "unknown"
    assert not result.healthy


def test_image_tag_matched_by_repository() -> None:
    app = healthy_application(image="ghcr.io/example/checkout-api:v9.9.9")
    result = evaluate_status(manifest(), app, alerts=[])
    assert result.image_tag == "v9.9.9"


def test_image_tag_unknown_when_repository_not_in_summary() -> None:
    app = healthy_application(image="ghcr.io/other/unrelated:v1.0.0")
    result = evaluate_status(manifest(), app, alerts=[])
    assert result.image_tag == "unknown"


def test_firing_alert_for_this_service_marks_unhealthy() -> None:
    # manifest() name is "checkout-api" -> alert prefix "CheckoutApi"
    alerts = [
        {"state": "firing", "labels": {"alertname": "CheckoutApiLatencyP99High"}},
    ]
    result = evaluate_status(manifest(), healthy_application(), alerts)
    assert not result.healthy
    assert result.firing_alerts == ["CheckoutApiLatencyP99High"]


def test_pending_alert_does_not_count_as_firing() -> None:
    alerts = [
        {"state": "pending", "labels": {"alertname": "CheckoutApiLatencyP99High"}},
    ]
    result = evaluate_status(manifest(), healthy_application(), alerts)
    assert result.healthy
    assert result.firing_alerts == []


def test_firing_alert_for_a_different_service_is_ignored() -> None:
    alerts = [
        {"state": "firing", "labels": {"alertname": "BillingWorkerErrorBudgetBurnFast"}},
    ]
    result = evaluate_status(manifest(), healthy_application(), alerts)
    assert result.healthy
    assert result.firing_alerts == []


def test_multiple_firing_alerts_are_deduplicated_and_sorted() -> None:
    alerts = [
        {"state": "firing", "labels": {"alertname": "CheckoutApiLatencyP99High"}},
        {"state": "firing", "labels": {"alertname": "CheckoutApiLatencyP99High"}},
        {"state": "firing", "labels": {"alertname": "CheckoutApiErrorBudgetBurnFast"}},
    ]
    result = evaluate_status(manifest(), healthy_application(), alerts)
    assert result.firing_alerts == ["CheckoutApiErrorBudgetBurnFast", "CheckoutApiLatencyP99High"]


def test_service_status_healthy_property_requires_all_three_conditions() -> None:
    assert ServiceStatus("svc", "Synced", "Healthy", "v1", []).healthy
    assert not ServiceStatus("svc", "OutOfSync", "Healthy", "v1", []).healthy
    assert not ServiceStatus("svc", "Synced", "Progressing", "v1", []).healthy
    assert not ServiceStatus("svc", "Synced", "Healthy", "v1", ["SomeAlert"]).healthy


def test_service_status_not_deployed_is_never_healthy_even_with_matching_strings() -> None:
    # deployed=False must win even if sync/health happen to read "Synced"/"Healthy".
    assert not ServiceStatus("svc", "Synced", "Healthy", "v1", [], deployed=False).healthy


# get_service_status: rendered-but-not-yet-deployed is normal, not an error;
# a genuine kubectl failure still is.


def test_get_service_status_reports_not_deployed_when_application_missing() -> None:
    with patch(
        "platformctl.status.fetch_application",
        side_effect=KubectlNotFoundError('applications.argoproj.io "checkout-api" not found'),
    ):
        result = get_service_status(manifest(), alerts=[])

    assert result.deployed is False
    assert not result.healthy
    assert result.sync_status == "NotDeployed"
    assert result.health_status == "NotDeployed"
    assert result.image_tag == "unknown"
    assert result.firing_alerts == []


def test_get_service_status_reraises_genuine_kubectl_failures() -> None:
    with patch("platformctl.status.fetch_application", side_effect=KubectlError("kubectl not found on PATH")):
        with pytest.raises(KubectlError):
            get_service_status(manifest(), alerts=[])
