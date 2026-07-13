"""Thin wrapper around `kubectl` for `platformctl status`.

Isolated in its own module so status.py's logic can be unit-tested against
fixture JSON without a real cluster — only this module ever shells out.
"""

import json
import subprocess


class KubectlError(RuntimeError):
    """kubectl was unavailable, failed, or returned unparsable output."""


class KubectlNotFoundError(KubectlError):
    """kubectl reported NotFound for the requested resource — the resource
    simply doesn't exist yet (e.g. an Application before ArgoCD's first
    sync), not a cluster/auth/network failure. A subclass of KubectlError so
    callers that don't care about the distinction can still catch it with a
    plain `except KubectlError`; callers that do care (status.py) catch this
    first.
    """


def kubectl_get_json(args: list[str]) -> dict:
    """Run `kubectl <args>` and parse its stdout as JSON.

    `args` is expected to request JSON output itself (`-o json`, or
    `get --raw` against a JSON API path) — this does not add `-o json`.
    """
    try:
        result = subprocess.run(
            ["kubectl", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise KubectlError("kubectl not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise KubectlError(f"kubectl {' '.join(args)} timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() if exc.stderr else f"exit code {exc.returncode}"
        # kubectl's own error format for a missing resource is always
        # "Error from server (NotFound): <kind> \"<name>\" not found" —
        # distinct from auth/network/timeout failures, which don't carry
        # "(NotFound)". Kept a text match rather than parsing `-o json`
        # error output because kubectl doesn't emit that here; it's a plain
        # stderr string regardless of the `-o json` requested for stdout.
        if exc.stderr and "(NotFound)" in exc.stderr:
            raise KubectlNotFoundError(f"kubectl {' '.join(args)} failed: {detail}") from exc
        raise KubectlError(f"kubectl {' '.join(args)} failed: {detail}") from exc

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise KubectlError(f"kubectl {' '.join(args)} did not return valid JSON") from exc
