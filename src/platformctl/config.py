from pathlib import Path

import yaml


def load_config(path: Path) -> dict:
    """Load platform/config.yaml — platform-wide settings such as the ArgoCD repo URL."""
    if not path.is_file():
        raise FileNotFoundError(path)
    return yaml.safe_load(path.read_text()) or {}


def get_argocd_repo_url(config: dict) -> str:
    return config["argocd"]["repo_url"]
