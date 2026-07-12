from pathlib import Path

import yaml
from typer.testing import CliRunner

from platformctl.cli import app
from platformctl.schema import ServiceManifest

runner = CliRunner()

TEAMS_YAML = """\
teams:
  - name: payments-team
  - name: platform-team
"""


def _init_root(tmp_path: Path) -> Path:
    (tmp_path / "platform").mkdir()
    (tmp_path / "platform" / "teams.yaml").write_text(TEAMS_YAML)
    return tmp_path


def test_init_scaffolds_valid_manifest(tmp_path: Path) -> None:
    root = _init_root(tmp_path)

    result = runner.invoke(
        app, ["init", "checkout-api", "--owner", "payments-team", "--tier", "1", "--root", str(root)]
    )

    assert result.exit_code == 0, result.output
    manifest_path = root / "services" / "checkout-api" / "service.yaml"
    assert manifest_path.is_file()

    data = yaml.safe_load(manifest_path.read_text())
    ServiceManifest.model_validate(data)  # scaffolded output must satisfy the schema
    assert data["tier"] == 1
    assert data["runtime"]["replicas"] == 3

    runbook_path = root / "docs" / "runbooks" / "checkout-api.md"
    assert runbook_path.is_file()


def test_init_applies_tier_based_defaults(tmp_path: Path) -> None:
    root = _init_root(tmp_path)

    result = runner.invoke(
        app, ["init", "batch-job", "--owner", "platform-team", "--tier", "3", "--root", str(root)]
    )

    assert result.exit_code == 0, result.output
    data = yaml.safe_load((root / "services" / "batch-job" / "service.yaml").read_text())
    assert data["runtime"]["replicas"] == 1
    assert data["slo"]["availability"] == 99.0


def test_init_unknown_owner_is_usage_error(tmp_path: Path) -> None:
    root = _init_root(tmp_path)

    result = runner.invoke(
        app, ["init", "checkout-api", "--owner", "ghost-team", "--root", str(root)]
    )

    assert result.exit_code == 2
    assert not (root / "services" / "checkout-api").exists()


def test_init_refuses_to_overwrite_existing_manifest(tmp_path: Path) -> None:
    root = _init_root(tmp_path)
    runner.invoke(app, ["init", "checkout-api", "--owner", "payments-team", "--root", str(root)])

    result = runner.invoke(
        app, ["init", "checkout-api", "--owner", "payments-team", "--root", str(root)]
    )

    assert result.exit_code == 2
