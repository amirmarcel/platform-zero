import re
from pathlib import Path
from typing import Optional

import typer
import yaml

from platformctl.cluster import KubectlError
from platformctl.config import get_argocd_repo_url, load_config
from platformctl.render import (
    check_drift,
    find_orphaned_artifacts,
    prune_orphaned_artifacts,
    render_artifacts,
    render_observability_artifact,
    write_artifacts,
)
from platformctl.schema import NAME_MAX_LENGTH, NAME_PATTERN
from platformctl.status import fetch_active_alerts, get_service_status
from platformctl.teams import InvalidTeamNameError, load_teams
from platformctl.validators import validate_manifest

_NAME_RE = re.compile(NAME_PATTERN)

app = typer.Typer(
    name="platformctl",
    help="CLI for the platform-zero internal developer platform.",
    no_args_is_help=True,
)

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
    except InvalidTeamNameError as exc:
        typer.echo(f"error: {exc}", err=True)
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


def _all_service_names(services_dir: Path) -> set[str]:
    """Every service currently declared under services/, by directory name —
    the set an artifact must belong to in order not to be orphaned.
    Independent of any --check/--prune target filter: a service not being
    rendered this invocation is still a service that exists.
    """
    if not services_dir.is_dir():
        return set()
    return {p.name for p in services_dir.iterdir() if p.is_dir() and (p / "service.yaml").is_file()}


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
    if not _NAME_RE.match(name) or len(name) > NAME_MAX_LENGTH:
        typer.echo(
            f"error: name '{name}' is not a valid service name "
            f"(must match {NAME_PATTERN} and be <={NAME_MAX_LENGTH} chars)",
            err=True,
        )
        raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)

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
    prune: bool = typer.Option(
        False,
        "--prune",
        help="Delete derived artifacts with no corresponding services/<name>/service.yaml, then exit.",
    ),
) -> None:
    """Generate Helm values, ArgoCD Application, Prometheus rules, and Grafana dashboard."""
    if check and prune:
        typer.echo("error: --check and --prune are mutually exclusive", err=True)
        raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)

    services_dir = root / "services"

    if prune:
        removed = prune_orphaned_artifacts(root, _all_service_names(services_dir))
        if removed:
            typer.echo("pruned:")
            for rel_path in removed:
                typer.echo(f"  - {rel_path}")
        else:
            typer.echo("no orphaned artifacts")
        raise typer.Exit(code=0)

    teams = _load_teams_or_exit(root / "platform" / "teams.yaml")
    config = _load_config_or_exit(root / "platform" / "config.yaml")
    repo_url = get_argocd_repo_url(config)
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

    if check:
        orphaned = find_orphaned_artifacts(root, _all_service_names(services_dir))
        if orphaned:
            any_drift = True
            typer.echo("ORPHAN")
            for rel_path in orphaned:
                typer.echo(f"  - {rel_path}")

    if any_invalid or (check and any_drift):
        raise typer.Exit(code=VALIDATION_FAILURE_EXIT_CODE)
    raise typer.Exit(code=0)


@app.command()
def status(
    name: Optional[str] = typer.Argument(
        None, help="Name of the service to check. Checks all services if omitted."
    ),
    root: Path = typer.Option(Path("."), "--root", help="Repository root."),
) -> None:
    """Show ArgoCD sync/health, the deployed image tag, and firing alerts."""
    teams = _load_teams_or_exit(root / "platform" / "teams.yaml")
    services_dir = root / "services"
    targets = _resolve_service_targets(name, services_dir)

    if not targets:
        typer.echo("no services found")
        raise typer.Exit(code=0)

    manifests = []
    for target in targets:
        manifest, errors = validate_manifest(target / "service.yaml", teams, root)
        if manifest is None or errors:
            typer.echo(
                f"error: {target.name}/service.yaml is invalid; run `platformctl validate` first",
                err=True,
            )
            raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)
        manifests.append(manifest)

    try:
        alerts = fetch_active_alerts()
    except KubectlError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)

    any_unhealthy = False
    for manifest in manifests:
        try:
            svc_status = get_service_status(manifest, alerts)
        except KubectlError as exc:
            typer.echo(f"error: {manifest.name}: {exc}", err=True)
            raise typer.Exit(code=USAGE_ERROR_EXIT_CODE)

        if not svc_status.healthy:
            any_unhealthy = True

        alerts_field = ", ".join(svc_status.firing_alerts) if svc_status.firing_alerts else "none"
        label = "OK" if svc_status.healthy else "DEGRADED"
        typer.echo(
            f"{label} {manifest.name}: sync={svc_status.sync_status} "
            f"health={svc_status.health_status} image={svc_status.image_tag} "
            f"alerts={alerts_field}"
        )

    raise typer.Exit(code=VALIDATION_FAILURE_EXIT_CODE if any_unhealthy else 0)


if __name__ == "__main__":
    app()
