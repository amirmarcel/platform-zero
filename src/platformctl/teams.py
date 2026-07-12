from pathlib import Path

import yaml


def load_teams(path: Path) -> set[str]:
    """Load the set of known team names from platform/teams.yaml."""
    if not path.is_file():
        raise FileNotFoundError(path)

    data = yaml.safe_load(path.read_text()) or {}
    teams = data.get("teams", [])
    return {team["name"] for team in teams}
