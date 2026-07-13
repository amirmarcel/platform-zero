from pathlib import Path

import yaml

from platformctl.render import render_artifacts
from platformctl.schema import ServiceManifest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "checkout-api"
REPO_URL = "https://github.com/example/platform-zero.git"

_ARTIFACT_TO_EXPECTED = {
    "helm/service/values/checkout-api.yaml": "values.yaml",
    "argocd/apps/checkout-api.yaml": "app.yaml",
    "observability/rules/checkout-api.yaml": "rules.yaml",
    "observability/dashboards/checkout-api.json": "dashboard.json",
}


def _load_fixture_manifest() -> ServiceManifest:
    data = yaml.safe_load((FIXTURE_DIR / "service.yaml").read_text())
    return ServiceManifest.model_validate(data)


def test_render_matches_golden_files() -> None:
    manifest = _load_fixture_manifest()
    artifacts = render_artifacts(manifest, REPO_URL)

    for rel_path, expected_name in _ARTIFACT_TO_EXPECTED.items():
        expected = (FIXTURE_DIR / "expected" / expected_name).read_bytes()
        assert artifacts[rel_path] == expected, f"drift in {rel_path}"


def test_render_is_byte_deterministic() -> None:
    manifest = _load_fixture_manifest()
    first = render_artifacts(manifest, REPO_URL)
    second = render_artifacts(_load_fixture_manifest(), REPO_URL)

    assert first.keys() == second.keys()
    for rel_path in first:
        assert first[rel_path] == second[rel_path], f"non-deterministic output for {rel_path}"
