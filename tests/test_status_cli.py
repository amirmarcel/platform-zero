from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from platformctl.cli import app
from platformctl.cluster import KubectlError

from conftest import valid_manifest

runner = CliRunner()

TEAMS_YAML = "teams:\n  - name: payments-team\n"


def _make_repo(tmp_path: Path, manifest: dict) -> Path:
    (tmp_path / "platform").mkdir()
    (tmp_path / "platform" / "teams.yaml").write_text(TEAMS_YAML)

    service_dir = tmp_path / "services" / manifest["name"]
    service_dir.mkdir(parents=True)
    (service_dir / "service.yaml").write_text(yaml.safe_dump(manifest))

    runbook_path = tmp_path / manifest["operations"]["runbook"]
    runbook_path.parent.mkdir(parents=True, exist_ok=True)
    runbook_path.write_text("# runbook\n")

    return tmp_path


def _healthy_application(image: str = "ghcr.io/example/checkout-api:v1.4.2") -> dict:
    return {
        "status": {
            "sync": {"status": "Synced"},
            "health": {"status": "Healthy"},
            "summary": {"images": [image]},
        }
    }


def test_status_healthy_service_exits_zero(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())

    with (
        patch("platformctl.cli.fetch_active_alerts", return_value=[]),
        patch("platformctl.cli.get_service_status") as mock_get_status,
    ):
        from platformctl.status import evaluate_status
        from platformctl.schema import ServiceManifest

        mock_get_status.side_effect = lambda manifest, alerts: evaluate_status(
            manifest, _healthy_application(), alerts
        )
        result = runner.invoke(app, ["status", "checkout-api", "--root", str(root)])

    assert result.exit_code == 0, result.output
    assert "OK checkout-api" in result.output
    assert "sync=Synced" in result.output
    assert "health=Healthy" in result.output
    assert "image=v1.4.2" in result.output
    assert "alerts=none" in result.output


def test_status_degraded_service_exits_one(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())
    app_json = _healthy_application()
    app_json["status"]["health"]["status"] = "Degraded"

    with (
        patch("platformctl.cli.fetch_active_alerts", return_value=[]),
        patch("platformctl.cli.get_service_status") as mock_get_status,
    ):
        from platformctl.status import evaluate_status

        mock_get_status.side_effect = lambda manifest, alerts: evaluate_status(manifest, app_json, alerts)
        result = runner.invoke(app, ["status", "checkout-api", "--root", str(root)])

    assert result.exit_code == 1
    assert "DEGRADED checkout-api" in result.output
    assert "health=Degraded" in result.output


def test_status_firing_alert_exits_one(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())
    alerts = [{"state": "firing", "labels": {"alertname": "CheckoutApiLatencyP99High"}}]

    with (
        patch("platformctl.cli.fetch_active_alerts", return_value=alerts),
        patch("platformctl.cli.get_service_status") as mock_get_status,
    ):
        from platformctl.status import evaluate_status

        mock_get_status.side_effect = lambda manifest, alerts: evaluate_status(
            manifest, _healthy_application(), alerts
        )
        result = runner.invoke(app, ["status", "checkout-api", "--root", str(root)])

    assert result.exit_code == 1
    assert "DEGRADED checkout-api" in result.output
    assert "alerts=CheckoutApiLatencyP99High" in result.output


def test_status_cluster_unreachable_is_usage_error(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())

    with patch("platformctl.cli.fetch_active_alerts", side_effect=KubectlError("kubectl not found on PATH")):
        result = runner.invoke(app, ["status", "checkout-api", "--root", str(root)])

    assert result.exit_code == 2
    assert "kubectl not found on PATH" in result.output


def test_status_application_not_found_is_informational_not_error(tmp_path: Path) -> None:
    # Rendered but not yet deployed — the normal state between `render` and
    # the first merge to main. Must not be reported as an error.
    root = _make_repo(tmp_path, valid_manifest())

    with (
        patch("platformctl.cli.fetch_active_alerts", return_value=[]),
        patch("platformctl.cli.get_service_status") as mock_get_status,
    ):
        from platformctl.status import ServiceStatus

        mock_get_status.return_value = ServiceStatus(
            name="checkout-api",
            sync_status="NotDeployed",
            health_status="NotDeployed",
            image_tag="unknown",
            firing_alerts=[],
            deployed=False,
        )
        result = runner.invoke(app, ["status", "checkout-api", "--root", str(root)])

    assert result.exit_code == 0, result.output
    assert "checkout-api: not deployed (no ArgoCD Application)" in result.output
    assert "error" not in result.output.lower()


def test_status_genuine_kubectl_failure_is_still_usage_error(tmp_path: Path) -> None:
    # A real cluster failure (auth, network, no kubectl) fetching this
    # service's Application must still fail loudly, distinct from NotFound.
    root = _make_repo(tmp_path, valid_manifest())

    with (
        patch("platformctl.cli.fetch_active_alerts", return_value=[]),
        patch(
            "platformctl.cli.get_service_status",
            side_effect=KubectlError("kubectl get application checkout-api -n argocd -o json failed: "
                                      "Unable to connect to the server"),
        ),
    ):
        result = runner.invoke(app, ["status", "checkout-api", "--root", str(root)])

    assert result.exit_code == 2
    assert "Unable to connect to the server" in result.output


def test_status_not_deployed_service_does_not_fail_the_run_for_other_healthy_services(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())

    second = valid_manifest()
    second["name"] = "billing-worker"
    service_dir = root / "services" / "billing-worker"
    service_dir.mkdir(parents=True)
    (service_dir / "service.yaml").write_text(yaml.safe_dump(second))

    from platformctl.status import ServiceStatus, evaluate_status

    def fake_get_status(manifest, alerts):
        if manifest.name == "checkout-api":
            return ServiceStatus(
                name="checkout-api",
                sync_status="NotDeployed",
                health_status="NotDeployed",
                image_tag="unknown",
                firing_alerts=[],
                deployed=False,
            )
        return evaluate_status(
            manifest, _healthy_application(image=f"{manifest.image.repository}:{manifest.image.tag}"), alerts
        )

    with (
        patch("platformctl.cli.fetch_active_alerts", return_value=[]),
        patch("platformctl.cli.get_service_status", side_effect=fake_get_status),
    ):
        result = runner.invoke(app, ["status", "--root", str(root)])

    assert result.exit_code == 0, result.output
    assert "checkout-api: not deployed (no ArgoCD Application)" in result.output
    assert "OK billing-worker" in result.output


def test_status_unknown_service_is_usage_error(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())
    result = runner.invoke(app, ["status", "does-not-exist", "--root", str(root)])
    assert result.exit_code == 2


def test_status_no_services_exits_zero(tmp_path: Path) -> None:
    (tmp_path / "platform").mkdir()
    (tmp_path / "platform" / "teams.yaml").write_text(TEAMS_YAML)
    (tmp_path / "services").mkdir()
    result = runner.invoke(app, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "no services found" in result.output


def test_status_all_services_reports_each(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())

    second = valid_manifest()
    second["name"] = "billing-worker"
    service_dir = root / "services" / "billing-worker"
    service_dir.mkdir(parents=True)
    (service_dir / "service.yaml").write_text(yaml.safe_dump(second))

    with (
        patch("platformctl.cli.fetch_active_alerts", return_value=[]),
        patch("platformctl.cli.get_service_status") as mock_get_status,
    ):
        from platformctl.status import evaluate_status

        mock_get_status.side_effect = lambda manifest, alerts: evaluate_status(
            manifest, _healthy_application(image=f"{manifest.image.repository}:{manifest.image.tag}"), alerts
        )
        result = runner.invoke(app, ["status", "--root", str(root)])

    assert result.exit_code == 0, result.output
    assert "OK checkout-api" in result.output
    assert "OK billing-worker" in result.output
