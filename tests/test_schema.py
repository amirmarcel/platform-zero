import pytest
from pydantic import ValidationError

from platformctl.schema import ServiceManifest

from conftest import valid_manifest


def test_valid_manifest_parses() -> None:
    ServiceManifest.model_validate(valid_manifest())


@pytest.mark.parametrize(
    "path,value",
    [
        (("apiVersion",), "platform/v2"),
        (("name",), ""),
        (("owner",), ""),
        (("tier",), 4),
    ],
)
def test_top_level_field_rejected(path, value) -> None:
    manifest = valid_manifest()
    manifest[path[0]] = value
    with pytest.raises(ValidationError):
        ServiceManifest.model_validate(manifest)


def test_missing_required_field_rejected() -> None:
    manifest = valid_manifest()
    del manifest["slo"]["window"]
    with pytest.raises(ValidationError):
        ServiceManifest.model_validate(manifest)


def test_missing_probes_rejected() -> None:
    manifest = valid_manifest()
    del manifest["runtime"]["probes"]["liveness"]
    with pytest.raises(ValidationError):
        ServiceManifest.model_validate(manifest)


def test_missing_resources_rejected() -> None:
    manifest = valid_manifest()
    del manifest["runtime"]["resources"]["limits"]
    with pytest.raises(ValidationError):
        ServiceManifest.model_validate(manifest)


def test_rollback_strategy_other_than_gitops_revert_rejected() -> None:
    manifest = valid_manifest()
    manifest["operations"]["rollback"] = "blue-green"
    with pytest.raises(ValidationError):
        ServiceManifest.model_validate(manifest)


def test_unknown_field_rejected() -> None:
    manifest = valid_manifest()
    manifest["extraField"] = "not allowed"
    with pytest.raises(ValidationError):
        ServiceManifest.model_validate(manifest)
