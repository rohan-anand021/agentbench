from types import SimpleNamespace
from pathlib import Path

import subprocess

from agentbench.sandbox.persistent_sandbox import PersistentDockerSandbox


def test_start_invokes_docker_run_with_tmpfs(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, capture_output=False, text=False, check=False):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="container123\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    sandbox = PersistentDockerSandbox(image="python:3.11", workdir="/workspace")
    sandbox.start()

    assert sandbox.container_id == "container123"
    assert any("--tmpfs" in arg for arg in calls[0])
    assert "python:3.11" in calls[0]


def test_exec_streams_output_to_files(monkeypatch, tmp_path: Path):
    calls: list[list[str]] = []

    def fake_run(args, stdout=None, stderr=None, timeout=None, **kwargs):
        calls.append(args)
        if stdout:
            stdout.write("out\n")
        if stderr:
            stderr.write("err\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    sandbox = PersistentDockerSandbox(image="python:3.11", workdir="/workspace")
    sandbox.container_id = "c1"

    out_path = tmp_path / "out.txt"
    err_path = tmp_path / "err.txt"

    result = sandbox.exec(
        command="echo hi",
        stdout_path=out_path,
        stderr_path=err_path,
        timeout_sec=5,
        network="none",
    )

    assert result.exit_code == 0
    assert out_path.read_text() == "out\n"
    assert err_path.read_text() == "err\n"
    assert "c1" in calls[-1]
    assert calls[-1][0:2] == ["docker", "exec"]


def test_cleanup_calls_docker_rm(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, check=False, capture_output=False):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    sandbox = PersistentDockerSandbox(image="python:3.11")
    sandbox.container_id = "c-clean"

    sandbox.cleanup()

    assert calls
    assert calls[-1][0:3] == ["docker", "rm", "-f"]
