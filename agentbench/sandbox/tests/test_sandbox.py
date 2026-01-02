from pathlib import Path

import pytest
from agentbench.sandbox.docker_sandbox import DockerSandbox

pytestmark = pytest.mark.docker


@pytest.fixture
def sandbox() -> DockerSandbox:
    return DockerSandbox(image="ghcr.io/agentbench/py-runner:0.1.0")


def test_python_version(sandbox, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_result = sandbox.run(
        workspace_host_path=workspace,
        command="python --version",
        network="none",
        stdout_path=tmp_path / "stdout.txt",
        stderr_path=tmp_path / "stderr.txt",
        timeout_sec=30,
    )

    with run_result.stdout_path.open("r") as stdout:
        assert "Python 3.11" in stdout.read()


def test_success_exit_code(sandbox, tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_result = sandbox.run(
        workspace_host_path=workspace,
        command="python --version",
        network="none",
        stdout_path=tmp_path / "stdout.txt",
        stderr_path=tmp_path / "stderr.txt",
        timeout_sec=30,
    )

    assert run_result.exit_code == 0
