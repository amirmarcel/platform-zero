from pathlib import Path
from typing import Optional

import typer
import yaml

from platformctl.config import get_argocd_repo_url, load_config
from platformctl.render import check_drift, render_artifacts, render_observability_artifact, write_artifacts
from platformctl.teams import load_teams
from platformctl.validators import validate_manifest

app = typer.Typer(
    name="platformctl",
    help="CLI for the platform-zero internal developer platform.",
    no_args_is_help=True,
)

NOT_IMPLEMENTED_EXIT_CODE = 3
USAGE_ERROR_EXIT_CODE = 2
VALIDATION_FAILURE_EXIT_CODE = 1

_TIER_DEFAULTS = {
    1: {
        "replicas": 3,
        "requests": {"cpu": "250m", "memory": "256Mi"},
        "limits": {"cpu": "1", "memory": "1Gi"},
        "availability": 99.9,
        "latency_p99_ms": 300,
    },
    2: {
        "replicas": 2,
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits": {"cpu": "500m", "memory": "512Mi"},
        "availability": 99.5,
        "latency_p99_ms": 500,
    },
    3: {
        "replicas": 1,
        "requests": {"cpu": "50m", "memory": "64Mi"},
        "limits": {"cpu": "250m", "memory": "256Mi"},
        "availability": 99.0,
        "latency_p99_ms": 1000,
    },
}


def _load_teams_or_exit(teams_path: Path) -> set[str]:
    try:
        return load_teams(teams_path)
    except FileNotFoundError:
        typer.echo(f"error: {teams_path} not found", err=True)
        raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)


def _load_config_or_exit(config_path: Path) -> dict:
    try:
        return load_config(config_path)
    except FileNotFoundError:
        typer.echo(f"error: {config_path} not found", err=True)
        raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)


def _resolve_service_targets(name: Optional[str], services_dir: Path) -> list[Path]:
    if name is not None:
        target = services_dir / name
        if not (target / "service.yaml").is_file():
            typer.echo(f"error: {target / 'service.yaml'} not found", err=True)
            raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)
        return [target]

    if not services_dir.is_dir():
        typer.echo(f"error: {services_dir} not found", err=True)
        raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)
    return sorted(p for p in services_dir.iterdir() if p.is_dir() and (p / "service.yaml").is_file())


@app.command()
def init(
    name: str = typer.Argument(..., help="Name of the service to scaffold."),
    owner: str = typer.Option(..., "--owner", help="Owning team; must exist in platform/teams.yaml."),
    tier: int = typer.Option(
        3, "--tier", min=1, max=3, help="Service tier: 1 (critical), 2 (internal), 3 (batch/async)."
    ),
    root: Path = typer.Option(Path("."), "--root", help="Repository root."),
) -> None:
    """Scaffold services/<name>/service.yaml with tier-based defaults."""
    teams = _load_teams_or_exit(root / "platform" / "teams.yaml")
    if owner not in teams:
        typer.echo(
            f"error: owner '{owner}' is not a known team. Known teams: {', '.join(sorted(teams))}",
            err=True,
        )
        raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)

    manifest_path = root / "services" / name / "service.yaml"
    if manifest_path.exists():
        typer.echo(f"error: {manifest_path} already exists", err=True)
        raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)

    defaults = _TIER_DEFAULTS[tier]
    runbook = f"docs/runbooks/{name}.md"
    manifest = {
        "apiVersion": "platform/v1",
        "name": name,
        "owner": owner,
        "tier": tier,
        "image": {
            "repository": f"ghcr.io/example/{name}",
            "tag": "v0.1.0",
        },
        "runtime": {
            "port": 8080,
            "replicas": defaults["replicas"],
            "resources": {
                "requests": defaults["requests"],
                "limits": defaults["limits"],
            },
            "probes": {
                "readiness": "/healthz/ready",
                "liveness": "/healthz/live",
            },
            "env": [],
        },
        "slo": {
            "availability": defaults["availability"],
            "latency_p99_ms": defaults["latency_p99_ms"],
            "window": "30d",
        },
        "operations": {
            "runbook": runbook,
            "rollback": "gitops-revert",
        },
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    runbook_path = root / runbook
    if not runbook_path.exists():
        runbook_path.parent.mkdir(parents=True, exist_ok=True)
        runbook_path.write_text(f"# Runbook: {name}\n\nTODO: document diagnosis and rollback steps.\n")

    typer.echo(f"scaffolded {manifest_path}")


@app.command()
def validate(
    name: Optional[str] = typer.Argument(
        None, help="Name of the service to validate. Validates all services if omitted."
    ),
    root: Path = typer.Option(Path("."), "--root", help="Repository root."),
) -> None:
    """Validate service.yaml against the schema and contract rules."""
    teams = _load_teams_or_exit(root / "platform" / "teams.yaml")
    services_dir = root / "services"
    targets = _resolve_service_targets(name, services_dir)

    if not targets:
        typer.echo("no services found")
        raise typer.Exit(code=0)

    any_failed = False
    for target in targets:
        _, errors = validate_manifest(target / "service.yaml", teams, root)
        if errors:
            any_failed = True
            typer.echo(f"FAIL {target.name}")
            for error in errors:
                typer.echo(f"  - {error}")
        else:
            typer.echo(f"PASS {target.name}")

    raise typer.Exit(code=VALIDATION_FAILURE_EXIT_CODE if any_failed else 0)


@app.command()
def render(
    name: Optional[str] = typer.Argument(
        None, help="Name of the service to render. Renders all services if omitted."
    ),
    root: Path = typer.Option(Path("."), "--root", help="Repository root."),
    check: bool = typer.Option(
        False,
        "--check",
        help="Render to memory and fail if the on-disk artifacts differ, without writing (drift check).",
    ),
) -> None:
    """Generate Helm values, ArgoCD Application, Prometheus rules, and Grafana dashboard."""
    teams = _load_teams_or_exit(root / "platform" / "teams.yaml")
    config = _load_config_or_exit(root / "platform" / "config.yaml")
    repo_url = get_argocd_repo_url(config)
    services_dir = root / "services"
    targets = _resolve_service_targets(name, services_dir)

    any_invalid = False
    any_drift = False

    # The observability Application is platform-owned, not derived from any
    # service manifest, so it renders even when no services exist.
    obs = render_observability_artifact(repo_url)
    if check:
        drifted = check_drift(root, obs)
        if drifted:
            any_drift = True
            typer.echo("DRIFT observability")
            for d in drifted:
                typer.echo(f"  - {d}")
        else:
            typer.echo("OK observability")
    else:
        write_artifacts(root, obs)
        typer.echo("rendered observability")

    if not targets:
        typer.echo("no services found")

    for target in targets:
        manifest, errors = validate_manifest(target / "service.yaml", teams, root)
        if manifest is None or errors:
            any_invalid = True
            typer.echo(f"INVALID {target.name}")
            for error in errors:
                typer.echo(f"  - {error}")
            continue

        artifacts = render_artifacts(manifest, repo_url)
        if check:
            drifted = check_drift(root, artifacts)
            if drifted:
                any_drift = True
                typer.echo(f"DRIFT {target.name}")
                for d in drifted:
                    typer.echo(f"  - {d}")
            else:
                typer.echo(f"OK {target.name}")
        else:
            write_artifacts(root, artifacts)
            typer.echo(f"rendered {target.name}")

    if any_invalid or (check and any_drift):
        raise typer.Exit(code=VALIDATION_FAILURE_EXIT_CODE)
    raise typer.Exit(code=0)


@app.command()
def status(
    name: Optional[str] = typer.Argument(
        None, help="Name of the service to check. Checks all services if omitted."
    ),
) -> None:
    """Show deployment and drift status for a service."""
    typer.echo("status: not implemented")
    raise typer.Exit(code=NOT_IMPLEMENTED_EXIT_CODE)


if __name__ == "__main__":
    app()
