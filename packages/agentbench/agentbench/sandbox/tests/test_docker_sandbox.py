"""Unit tests for DockerSandbox.

These tests verify the command building and error handling logic
without requiring Docker to be installed (unit tests with mocking).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from agentbench.sandbox.docker_sandbox import DockerRunResult, DockerSandbox


class TestDockerSandboxInit:
    """Tests for DockerSandbox initialization."""

    def test_init_with_defaults(self):
        """DockerSandbox initializes with default workdir."""
        sandbox = DockerSandbox(image="python:3.11")
        assert sandbox.image == "python:3.11"
        assert sandbox.workdir == "/workspace"

    def test_init_with_custom_workdir(self):
        """DockerSandbox accepts custom workdir."""
        sandbox = DockerSandbox(image="node:18", workdir="/app")
        assert sandbox.image == "node:18"
        assert sandbox.workdir == "/app"


class TestDockerSandboxNetworkValidation:
    """Tests for network mode validation."""

    def test_invalid_network_raises_value_error(self, tmp_path: Path):
        """Invalid network mode raises ValueError."""
        sandbox = DockerSandbox(image="python:3.11")
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with pytest.raises(ValueError, match="Network must be 'none' or 'bridge'"):
            sandbox.run(
                workspace_host_path=workspace,
                command="echo hello",
                network="host",  # Invalid
                timeout_sec=30,
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=tmp_path / "stderr.txt",
            )

    def test_none_network_is_valid(self, tmp_path: Path):
        """Network 'none' is accepted."""
        sandbox = DockerSandbox(image="python:3.11")
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = sandbox.run(
                workspace_host_path=workspace,
                command="echo hello",
                network="none",
                timeout_sec=30,
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=tmp_path / "stderr.txt",
            )
            assert result.exit_code == 0

    def test_bridge_network_is_valid(self, tmp_path: Path):
        """Network 'bridge' is accepted."""
        sandbox = DockerSandbox(image="python:3.11")
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = sandbox.run(
                workspace_host_path=workspace,
                command="echo hello",
                network="bridge",
                timeout_sec=30,
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=tmp_path / "stderr.txt",
            )
            assert result.exit_code == 0


class TestDockerSandboxWorkspaceValidation:
    """Tests for workspace path validation."""

    def test_nonexistent_workspace_raises_value_error(self, tmp_path: Path):
        """Non-existent workspace path raises ValueError."""
        sandbox = DockerSandbox(image="python:3.11")
        nonexistent = tmp_path / "does_not_exist"

        with pytest.raises(
            ValueError, match="Workspace host path directory does not exist"
        ):
            sandbox.run(
                workspace_host_path=nonexistent,
                command="echo hello",
                network="none",
                timeout_sec=30,
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=tmp_path / "stderr.txt",
            )


class TestDockerSandboxCommandBuilding:
    """Tests for Docker command building."""

    def test_builds_correct_docker_command(self, tmp_path: Path):
        """Verify the Docker command is built correctly."""
        sandbox = DockerSandbox(image="python:3.11", workdir="/workspace")
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            sandbox.run(
                workspace_host_path=workspace,
                command="pytest tests/",
                network="none",
                timeout_sec=60,
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=tmp_path / "stderr.txt",
            )

            # Verify the command was called with correct arguments
            call_args = mock_run.call_args
            cmd = call_args.kwargs.get("args") or call_args[1].get("args")

            assert cmd[0] == "docker"
            assert cmd[1] == "run"
            assert "--rm" in cmd
            assert "--network" in cmd
            assert "none" in cmd
            assert "-v" in cmd
            assert "-w" in cmd
            assert "/workspace" in cmd
            assert "python:3.11" in cmd
            assert "bash" in cmd
            assert "-lc" in cmd
            assert "pytest tests/" in cmd


class TestDockerSandboxTimeout:
    """Tests for timeout handling."""

    def test_timeout_returns_exit_code_124(self, tmp_path: Path):
        """Timeout returns exit code 124."""
        import subprocess

        sandbox = DockerSandbox(image="python:3.11")
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=30)
            result = sandbox.run(
                workspace_host_path=workspace,
                command="sleep 100",
                network="none",
                timeout_sec=30,
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=tmp_path / "stderr.txt",
            )

            assert result.exit_code == 124

    def test_timeout_appends_message_to_stderr(self, tmp_path: Path):
        """Timeout message is appended to stderr file."""
        import subprocess

        sandbox = DockerSandbox(image="python:3.11")
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        stderr_path = tmp_path / "stderr.txt"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=30)
            sandbox.run(
                workspace_host_path=workspace,
                command="sleep 100",
                network="none",
                timeout_sec=30,
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=stderr_path,
            )

            content = stderr_path.read_text()
            assert "timed out" in content
            assert "30" in content


class TestDockerSandboxExitCodes:
    """Tests for exit code handling."""

    def test_success_returns_exit_code_0(self, tmp_path: Path):
        """Successful command returns exit code 0."""
        sandbox = DockerSandbox(image="python:3.11")
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = sandbox.run(
                workspace_host_path=workspace,
                command="echo hello",
                network="none",
                timeout_sec=30,
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=tmp_path / "stderr.txt",
            )

            assert result.exit_code == 0

    def test_failure_returns_nonzero_exit_code(self, tmp_path: Path):
        """Failed command returns non-zero exit code."""
        sandbox = DockerSandbox(image="python:3.11")
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = sandbox.run(
                workspace_host_path=workspace,
                command="exit 1",
                network="none",
                timeout_sec=30,
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=tmp_path / "stderr.txt",
            )

            assert result.exit_code == 1


class TestDockerSandboxOutputPaths:
    """Tests for output file path handling."""

    def test_creates_parent_directories_for_output(self, tmp_path: Path):
        """Output directories are created if they don't exist."""
        sandbox = DockerSandbox(image="python:3.11")
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        stdout_path = tmp_path / "logs" / "nested" / "stdout.txt"
        stderr_path = tmp_path / "logs" / "nested" / "stderr.txt"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            sandbox.run(
                workspace_host_path=workspace,
                command="echo hello",
                network="none",
                timeout_sec=30,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )

            assert stdout_path.parent.exists()
            assert stderr_path.parent.exists()

    def test_result_contains_correct_paths(self, tmp_path: Path):
        """DockerRunResult contains the correct output paths."""
        sandbox = DockerSandbox(image="python:3.11")
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        stdout_path = tmp_path / "stdout.txt"
        stderr_path = tmp_path / "stderr.txt"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = sandbox.run(
                workspace_host_path=workspace,
                command="echo hello",
                network="none",
                timeout_sec=30,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )

            assert result.stdout_path == stdout_path
            assert result.stderr_path == stderr_path


class TestDockerRunResult:
    """Tests for DockerRunResult dataclass."""

    def test_docker_run_result_fields(self, tmp_path: Path):
        """DockerRunResult has correct fields."""
        result = DockerRunResult(
            exit_code=0,
            stdout_path=tmp_path / "stdout.txt",
            stderr_path=tmp_path / "stderr.txt",
        )

        assert result.exit_code == 0
        assert result.stdout_path == tmp_path / "stdout.txt"
        assert result.stderr_path == tmp_path / "stderr.txt"
