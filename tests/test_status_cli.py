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


def test_status_application_not_found_is_usage_error(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())

    with (
        patch("platformctl.cli.fetch_active_alerts", return_value=[]),
        patch("platformctl.cli.get_service_status", side_effect=KubectlError("applications.argoproj.io not found")),
    ):
        result = runner.invoke(app, ["status", "checkout-api", "--root", str(root)])

    assert result.exit_code == 2
    assert "not found" in result.output


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
