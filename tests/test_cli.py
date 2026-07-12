from typer.testing import CliRunner

from platformctl.cli import app

runner = CliRunner()


def test_help_runs_and_lists_subcommands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for subcommand in ("init", "validate", "render", "status"):
        assert subcommand in result.output


def test_render_and_status_are_still_stubs() -> None:
    assert runner.invoke(app, ["render"]).exit_code == 3
    assert runner.invoke(app, ["status"]).exit_code == 3
