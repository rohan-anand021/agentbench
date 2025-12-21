from pathlib import Path

import pytest

from agentbench.sandbox.docker_sandbox import DockerSandbox


@pytest.fixture
def sandbox() -> DockerSandbox:
    return DockerSandbox(image="ghcr.io/agentbench/py-runner:0.1.0")


def test_python_version(sandbox):
    run_result = sandbox.run(
        workspace_host_path=Path("../temp_dir_whp"),
        command="python --version",
        network="none",
        stdout_path=Path("../temp_dir_whp/temp_dir_stdout_path.txt"),
        stderr_path=Path("../temp_dir_whp/temp_dir_stderr_path.txt"),
        timeout_sec=30,
    )

    with run_result.stdout_path.open("r") as stdout:
        assert "Python 3.11" in stdout.read()


def test_success_exit_code(sandbox):
    run_result = sandbox.run(
        workspace_host_path=Path("../temp_dir_whp"),
        command="python --version",
        network="none",
        stdout_path=Path("../temp_dir_whp/temp_dir_stdout_path.txt"),
        stderr_path=Path("../temp_dir_whp/temp_dir_stderr_path.txt"),
        timeout_sec=30,
    )

    assert run_result.exit_code == 0
