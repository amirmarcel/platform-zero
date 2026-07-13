from pathlib import Path

import pytest

from platformctl.schema import ServiceManifest
from platformctl.validators import (
    validate_image_tag,
    validate_manifest,
    validate_owner_exists,
    validate_resource_limits,
    validate_runbook_exists,
)

from conftest import valid_manifest

TEAMS = {"payments-team", "platform-team", "checkout-team"}


def manifest(overrides: dict | None = None) -> ServiceManifest:
    data = valid_manifest()
    if overrides:
        data.update(overrides)
    return ServiceManifest.model_validate(data)


# Rule 3: immutable image tag


def test_image_tag_valid_semver_passes() -> None:
    assert validate_image_tag(manifest()) == []


@pytest.mark.parametrize("tag", ["latest", "LATEST", "main", "dev", "v1", "1.2"])
def test_image_tag_latest_or_unpinned_rejected(tag: str) -> None:
    m = manifest()
    m.image.tag = tag
    errors = validate_image_tag(m)
    assert errors


# Rule 4: limits >= requests


def test_resource_limits_meeting_requests_passes() -> None:
    assert validate_resource_limits(manifest()) == []


def test_resource_limits_below_requests_cpu_rejected() -> None:
    m = manifest()
    m.runtime.resources.requests.cpu = "500m"
    m.runtime.resources.limits.cpu = "100m"
    errors = validate_resource_limits(m)
    assert any("cpu" in e for e in errors)


def test_resource_limits_below_requests_memory_rejected() -> None:
    m = manifest()
    m.runtime.resources.requests.memory = "512Mi"
    m.runtime.resources.limits.memory = "128Mi"
    errors = validate_resource_limits(m)
    assert any("memory" in e for e in errors)


# Rule 1: owner must exist in platform/teams.yaml


def test_owner_known_team_passes() -> None:
    assert validate_owner_exists(manifest(), TEAMS) == []


def test_owner_unknown_team_rejected() -> None:
    m = manifest()
    m.owner = "ghost-team"
    errors = validate_owner_exists(m, TEAMS)
    assert errors


# Rule 8: runbook must exist


def test_runbook_exists_passes(tmp_path: Path) -> None:
    runbook = tmp_path / "docs" / "runbooks" / "checkout-api.md"
    runbook.parent.mkdir(parents=True)
    runbook.write_text("# runbook\n")
    assert validate_runbook_exists(manifest(), tmp_path) == []


def test_runbook_missing_rejected(tmp_path: Path) -> None:
    errors = validate_runbook_exists(manifest(), tmp_path)
    assert errors


# validate_manifest integration


def test_validate_manifest_passes_for_valid_service(tmp_path: Path) -> None:
    service_path = tmp_path / "service.yaml"
    import yaml

    service_path.write_text(yaml.safe_dump(valid_manifest()))
    runbook = tmp_path / "docs" / "runbooks" / "checkout-api.md"
    runbook.parent.mkdir(parents=True)
    runbook.write_text("# runbook\n")

    parsed, errors = validate_manifest(service_path, TEAMS, tmp_path)
    assert errors == []
    assert parsed is not None


def test_validate_manifest_rejects_name_that_violates_rfc1123_pattern(tmp_path: Path) -> None:
    import yaml

    data = valid_manifest()
    data["name"] = "Bad_Name"
    service_path = tmp_path / "service.yaml"
    service_path.write_text(yaml.safe_dump(data))

    parsed, errors = validate_manifest(service_path, TEAMS, tmp_path)
    assert parsed is None
    assert any("name" in e for e in errors)


def test_validate_manifest_reports_multiple_failures(tmp_path: Path) -> None:
    import yaml

    data = valid_manifest()
    data["owner"] = "ghost-team"
    data["image"]["tag"] = "latest"
    service_path = tmp_path / "service.yaml"
    service_path.write_text(yaml.safe_dump(data))
    # runbook intentionally not created

    parsed, errors = validate_manifest(service_path, TEAMS, tmp_path)
    assert parsed is not None
    assert len(errors) >= 3
