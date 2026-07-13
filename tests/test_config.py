from pathlib import Path

import pytest

from platformctl.config import get_argocd_repo_url, load_config


def test_load_config_reads_argocd_repo_url(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("argocd:\n  repo_url: https://example.invalid/platform-zero.git\n")

    config = load_config(config_path)

    assert get_argocd_repo_url(config) == "https://example.invalid/platform-zero.git"


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does-not-exist.yaml")
