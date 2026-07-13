import re
from pathlib import Path

import yaml

# Team names are rendered as the value of the `platform.io/owner` Kubernetes
# label (render.py), so they must satisfy Kubernetes label-value grammar:
# <=63 chars, alphanumeric start/end, interior alphanumerics plus -_. only.
_LABEL_VALUE_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9_.-]{0,61}[A-Za-z0-9])?$")


class InvalidTeamNameError(ValueError):
    """Raised when platform/teams.yaml declares a name that is not a valid
    Kubernetes label value."""


def load_teams(path: Path) -> set[str]:
    """Load the set of known team names from platform/teams.yaml."""
    if not path.is_file():
        raise FileNotFoundError(path)

    data = yaml.safe_load(path.read_text()) or {}
    teams = data.get("teams", [])
    names = {team["name"] for team in teams}

    invalid = sorted(name for name in names if not _LABEL_VALUE_RE.match(name))
    if invalid:
        raise InvalidTeamNameError(
            f"{path}: invalid team name(s) {invalid} — must be <=63 chars, "
            "alphanumeric start/end, interior -_. allowed (Kubernetes label-value grammar)"
        )

    return names
