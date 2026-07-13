"""Thin wrapper around `kubectl` for `platformctl status`.

Isolated in its own module so status.py's logic can be unit-tested against
fixture JSON without a real cluster — only this module ever shells out.
"""

import json
import subprocess


class KubectlError(RuntimeError):
    """kubectl was unavailable, failed, or returned unparsable output."""


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
        raise KubectlError(f"kubectl {' '.join(args)} failed: {detail}") from exc

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise KubectlError(f"kubectl {' '.join(args)} did not return valid JSON") from exc
