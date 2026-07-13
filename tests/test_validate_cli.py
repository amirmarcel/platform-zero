from pathlib import Path

import yaml
from typer.testing import CliRunner

from platformctl.cli import app

from conftest import valid_manifest

runner = CliRunner()

TEAMS_YAML = """\
teams:
  - name: payments-team
  - name: platform-team
"""


def _make_repo(tmp_path: Path, manifest: dict, with_runbook: bool = True) -> Path:
    (tmp_path / "platform").mkdir()
    (tmp_path / "platform" / "teams.yaml").write_text(TEAMS_YAML)

    service_dir = tmp_path / "services" / manifest["name"]
    service_dir.mkdir(parents=True)
    (service_dir / "service.yaml").write_text(yaml.safe_dump(manifest))

    if with_runbook:
        runbook_path = tmp_path / manifest["operations"]["runbook"]
        runbook_path.parent.mkdir(parents=True, exist_ok=True)
        runbook_path.write_text("# runbook\n")

    return tmp_path


def test_validate_passes_for_conformant_service(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())
    result = runner.invoke(app, ["validate", "checkout-api", "--root", str(root)])
    assert result.exit_code == 0
    assert "PASS checkout-api" in result.output


def test_validate_fails_for_missing_runbook(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest(), with_runbook=False)
    result = runner.invoke(app, ["validate", "checkout-api", "--root", str(root)])
    assert result.exit_code == 1
    assert "FAIL checkout-api" in result.output


def test_validate_unknown_service_is_usage_error(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())
    result = runner.invoke(app, ["validate", "does-not-exist", "--root", str(root)])
    assert result.exit_code == 2


def test_validate_missing_teams_file_is_usage_error(tmp_path: Path) -> None:
    service_dir = tmp_path / "services" / "checkout-api"
    service_dir.mkdir(parents=True)
    (service_dir / "service.yaml").write_text(yaml.safe_dump(valid_manifest()))

    result = runner.invoke(app, ["validate", "checkout-api", "--root", str(tmp_path)])
    assert result.exit_code == 2


def test_validate_rejects_name_that_violates_rfc1123_pattern(tmp_path: Path) -> None:
    manifest = valid_manifest()
    manifest["name"] = "Bad_Name"
    root = _make_repo(tmp_path, manifest)

    result = runner.invoke(app, ["validate", "Bad_Name", "--root", str(root)])

    assert result.exit_code == 1
    assert "FAIL Bad_Name" in result.output
    assert "name" in result.output.lower()


def test_validate_all_services_reports_each(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())

    second = valid_manifest()
    second["name"] = "billing-worker"
    second["owner"] = "ghost-team"
    service_dir = root / "services" / "billing-worker"
    service_dir.mkdir(parents=True)
    (service_dir / "service.yaml").write_text(yaml.safe_dump(second))

    result = runner.invoke(app, ["validate", "--root", str(root)])
    assert result.exit_code == 1
    assert "PASS checkout-api" in result.output
    assert "FAIL billing-worker" in result.output
