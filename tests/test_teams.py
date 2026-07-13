from pathlib import Path

import pytest
import yaml

from platformctl.teams import InvalidTeamNameError, load_teams


def _write_teams(tmp_path: Path, names: list[str]) -> Path:
    path = tmp_path / "teams.yaml"
    path.write_text(yaml.safe_dump({"teams": [{"name": n, "slack": "#x"} for n in names]}))
    return path


def test_load_teams_accepts_valid_label_values(tmp_path: Path) -> None:
    path = _write_teams(tmp_path, ["payments-team", "platform_team", "checkout.team", "a"])
    assert load_teams(path) == {"payments-team", "platform_team", "checkout.team", "a"}


def test_load_teams_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_teams(tmp_path / "does-not-exist.yaml")


@pytest.mark.parametrize(
    "name",
    [
        "-payments-team",  # cannot start with -
        "payments-team-",  # cannot end with -
        "payments team",  # whitespace not allowed
        "a" * 64,  # exceeds the 63-char label-value limit
    ],
)
def test_load_teams_rejects_invalid_label_value(tmp_path: Path, name: str) -> None:
    path = _write_teams(tmp_path, [name])
    with pytest.raises(InvalidTeamNameError):
        load_teams(path)
