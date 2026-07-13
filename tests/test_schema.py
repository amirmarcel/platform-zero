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


@pytest.mark.parametrize(
    "name",
    [
        "Checkout-Api",  # uppercase not allowed
        "checkout_api",  # underscore not allowed
        "-checkout-api",  # cannot start with a hyphen
        "checkout-api-",  # cannot end with a hyphen
        "checkout api",  # whitespace not allowed
        "a" * 54,  # exceeds Helm's 53-char release-name limit
    ],
)
def test_name_rejected_when_not_rfc1123_label(name: str) -> None:
    manifest = valid_manifest()
    manifest["name"] = name
    with pytest.raises(ValidationError):
        ServiceManifest.model_validate(manifest)


def test_name_max_length_accepted() -> None:
    manifest = valid_manifest()
    manifest["name"] = "a" * 53
    ServiceManifest.model_validate(manifest)


def test_availability_of_100_rejected() -> None:
    manifest = valid_manifest()
    manifest["slo"]["availability"] = 100
    with pytest.raises(ValidationError):
        ServiceManifest.model_validate(manifest)


def test_availability_of_zero_rejected() -> None:
    manifest = valid_manifest()
    manifest["slo"]["availability"] = 0
    with pytest.raises(ValidationError):
        ServiceManifest.model_validate(manifest)
