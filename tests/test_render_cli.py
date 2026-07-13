from pathlib import Path

import yaml
from typer.testing import CliRunner

from platformctl.cli import app

from conftest import valid_manifest

runner = CliRunner()

TEAMS_YAML = "teams:\n  - name: payments-team\n"
CONFIG_YAML = "argocd:\n  repo_url: https://example.invalid/platform-zero.git\n"


def _make_repo(tmp_path: Path, manifest: dict) -> Path:
    (tmp_path / "platform").mkdir()
    (tmp_path / "platform" / "teams.yaml").write_text(TEAMS_YAML)
    (tmp_path / "platform" / "config.yaml").write_text(CONFIG_YAML)

    service_dir = tmp_path / "services" / manifest["name"]
    service_dir.mkdir(parents=True)
    (service_dir / "service.yaml").write_text(yaml.safe_dump(manifest))

    runbook_path = tmp_path / manifest["operations"]["runbook"]
    runbook_path.parent.mkdir(parents=True, exist_ok=True)
    runbook_path.write_text("# runbook\n")

    return tmp_path


def test_render_writes_all_four_artifacts(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())

    result = runner.invoke(app, ["render", "checkout-api", "--root", str(root)])

    assert result.exit_code == 0, result.output
    assert (root / "helm" / "service" / "values" / "checkout-api.yaml").is_file()
    assert (root / "argocd" / "apps" / "checkout-api.yaml").is_file()
    assert (root / "observability" / "rules" / "checkout-api.yaml").is_file()
    assert (root / "observability" / "dashboards" / "checkout-api.json").is_file()


def test_render_writes_observability_application(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())

    result = runner.invoke(app, ["render", "checkout-api", "--root", str(root)])

    assert result.exit_code == 0, result.output
    obs_path = root / "argocd" / "apps" / "observability.yaml"
    assert obs_path.is_file()
    obs = yaml.safe_load(obs_path.read_text())
    assert obs["spec"]["source"]["repoURL"] == "https://example.invalid/platform-zero.git"
    assert obs["spec"]["source"]["path"] == "observability"


def test_render_observability_is_rendered_with_zero_services(tmp_path: Path) -> None:
    (tmp_path / "platform").mkdir()
    (tmp_path / "platform" / "teams.yaml").write_text(TEAMS_YAML)
    (tmp_path / "platform" / "config.yaml").write_text(CONFIG_YAML)
    (tmp_path / "services").mkdir()

    result = runner.invoke(app, ["render", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "argocd" / "apps" / "observability.yaml").is_file()


def test_render_check_fails_when_observability_application_tampered(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())
    runner.invoke(app, ["render", "checkout-api", "--root", str(root)])

    obs_path = root / "argocd" / "apps" / "observability.yaml"
    obs = yaml.safe_load(obs_path.read_text())
    obs["spec"]["source"]["path"] = "tampered"
    obs_path.write_text(yaml.safe_dump(obs))

    result = runner.invoke(app, ["render", "checkout-api", "--check", "--root", str(root)])

    assert result.exit_code == 1
    assert "DRIFT observability" in result.output


def test_render_check_fails_with_zero_services_when_observability_drifted(tmp_path: Path) -> None:
    (tmp_path / "platform").mkdir()
    (tmp_path / "platform" / "teams.yaml").write_text(TEAMS_YAML)
    (tmp_path / "platform" / "config.yaml").write_text(CONFIG_YAML)
    (tmp_path / "services").mkdir()

    result = runner.invoke(app, ["render", "--check", "--root", str(tmp_path)])

    assert result.exit_code == 1
    assert "DRIFT observability" in result.output


def test_render_check_passes_when_artifacts_are_up_to_date(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())
    runner.invoke(app, ["render", "checkout-api", "--root", str(root)])

    result = runner.invoke(app, ["render", "checkout-api", "--check", "--root", str(root)])

    assert result.exit_code == 0, result.output
    assert "OK checkout-api" in result.output


def test_render_check_fails_when_artifact_missing(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())

    result = runner.invoke(app, ["render", "checkout-api", "--check", "--root", str(root)])

    assert result.exit_code == 1
    assert "DRIFT checkout-api" in result.output
    # --check must not write anything
    assert not (root / "helm" / "service" / "values" / "checkout-api.yaml").exists()


def test_render_check_fails_when_manifest_changed_after_render(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())
    runner.invoke(app, ["render", "checkout-api", "--root", str(root)])

    manifest_path = root / "services" / "checkout-api" / "service.yaml"
    data = yaml.safe_load(manifest_path.read_text())
    data["image"]["tag"] = "v2.0.0"
    manifest_path.write_text(yaml.safe_dump(data))

    result = runner.invoke(app, ["render", "checkout-api", "--check", "--root", str(root)])

    assert result.exit_code == 1
    assert "DRIFT checkout-api" in result.output


def test_render_missing_config_is_usage_error(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, valid_manifest())
    (root / "platform" / "config.yaml").unlink()

    result = runner.invoke(app, ["render", "checkout-api", "--root", str(root)])

    assert result.exit_code == 2


def test_render_refuses_invalid_manifest(tmp_path: Path) -> None:
    data = valid_manifest()
    data["image"]["tag"] = "latest"
    root = _make_repo(tmp_path, data)

    result = runner.invoke(app, ["render", "checkout-api", "--root", str(root)])

    assert result.exit_code == 1
    assert "INVALID checkout-api" in result.output
    assert not (root / "helm" / "service" / "values" / "checkout-api.yaml").exists()
