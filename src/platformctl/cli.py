import typer

app = typer.Typer(
    name="platformctl",
    help="CLI for the platform-zero internal developer platform.",
    no_args_is_help=True,
)

NOT_IMPLEMENTED_EXIT_CODE = 3


@app.command()
def init(name: str = typer.Argument(..., help="Name of the service to scaffold.")) -> None:
    """Scaffold services/<name>/service.yaml with tier-based defaults."""
    typer.echo("init: not implemented")
    raise typer.Exit(code=NOT_IMPLEMENTED_EXIT_CODE)


@app.command()
def validate(
    name: str = typer.Argument(None, help="Name of the service to validate. Validates all services if omitted."),
) -> None:
    """Validate service.yaml against the schema and contract rules."""
    typer.echo("validate: not implemented")
    raise typer.Exit(code=NOT_IMPLEMENTED_EXIT_CODE)


@app.command()
def render(
    name: str = typer.Argument(None, help="Name of the service to render. Renders all services if omitted."),
) -> None:
    """Generate Helm values, ArgoCD Application, Prometheus rules, and Grafana dashboard."""
    typer.echo("render: not implemented")
    raise typer.Exit(code=NOT_IMPLEMENTED_EXIT_CODE)


@app.command()
def status(
    name: str = typer.Argument(None, help="Name of the service to check. Checks all services if omitted."),
) -> None:
    """Show deployment and drift status for a service."""
    typer.echo("status: not implemented")
    raise typer.Exit(code=NOT_IMPLEMENTED_EXIT_CODE)


if __name__ == "__main__":
    app()
