import subprocess
from unittest.mock import patch

import pytest

from platformctl.cluster import KubectlError, KubectlNotFoundError, kubectl_get_json


def _completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["kubectl"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_kubectl_get_json_parses_stdout() -> None:
    with patch("subprocess.run", return_value=_completed('{"status": "ok"}')) as mock_run:
        result = kubectl_get_json(["get", "thing", "-o", "json"])
    assert result == {"status": "ok"}
    assert mock_run.call_args.args[0] == ["kubectl", "get", "thing", "-o", "json"]


def test_kubectl_not_on_path_raises_kubectl_error() -> None:
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(KubectlError):
            kubectl_get_json(["get", "thing"])


def test_kubectl_timeout_raises_kubectl_error() -> None:
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="kubectl", timeout=15)):
        with pytest.raises(KubectlError):
            kubectl_get_json(["get", "thing"])


def test_kubectl_nonzero_exit_raises_kubectl_error() -> None:
    err = subprocess.CalledProcessError(returncode=1, cmd="kubectl", stderr="applications.argoproj.io not found")
    with patch("subprocess.run", side_effect=err):
        with pytest.raises(KubectlError, match="not found"):
            kubectl_get_json(["get", "application", "ghost"])


def test_kubectl_invalid_json_raises_kubectl_error() -> None:
    with patch("subprocess.run", return_value=_completed("not json")):
        with pytest.raises(KubectlError):
            kubectl_get_json(["get", "thing", "-o", "json"])


# Distinguishing "resource not found" from a genuine kubectl failure


def test_kubectl_notfound_stderr_raises_notfound_subclass() -> None:
    err = subprocess.CalledProcessError(
        returncode=1,
        cmd="kubectl",
        stderr='Error from server (NotFound): applications.argoproj.io "payments-api" not found',
    )
    with patch("subprocess.run", side_effect=err):
        with pytest.raises(KubectlNotFoundError):
            kubectl_get_json(["get", "application", "payments-api", "-n", "argocd", "-o", "json"])


def test_kubectl_notfound_subclass_is_still_a_kubectl_error() -> None:
    err = subprocess.CalledProcessError(
        returncode=1,
        cmd="kubectl",
        stderr='Error from server (NotFound): applications.argoproj.io "payments-api" not found',
    )
    with patch("subprocess.run", side_effect=err):
        with pytest.raises(KubectlError):
            kubectl_get_json(["get", "application", "payments-api", "-n", "argocd", "-o", "json"])


@pytest.mark.parametrize(
    "stderr",
    [
        "Unable to connect to the server: dial tcp: i/o timeout",
        "error: You must be logged in to the server (Unauthorized)",
        "",
    ],
)
def test_kubectl_genuine_failure_does_not_raise_notfound_subclass(stderr: str) -> None:
    err = subprocess.CalledProcessError(returncode=1, cmd="kubectl", stderr=stderr)
    with patch("subprocess.run", side_effect=err):
        with pytest.raises(KubectlError) as exc_info:
            kubectl_get_json(["get", "application", "payments-api", "-n", "argocd", "-o", "json"])
    assert not isinstance(exc_info.value, KubectlNotFoundError)
