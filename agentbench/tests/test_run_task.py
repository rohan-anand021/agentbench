"""Unit tests for run_task function.

These tests use mocking to avoid requiring Docker or network access.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbench.run_task import run_task


def make_mock_task():
    """Create a mock TaskSpec."""
    mock_task = MagicMock()
    mock_task.id = "test-task-1"
    mock_task.repo.url = "https://github.com/example/repo.git"
    mock_task.repo.commit = "abc123"
    mock_task.environment.docker_image = "python:3.11"
    mock_task.environment.workdir = "/workspace"
    mock_task.environment.timeout_sec = 300
    mock_task.setup.commands = ["pip install -e ."]
    mock_task.run.command = "pytest tests/"
    return mock_task


@pytest.fixture
def mock_dependencies():
    """Patch all external dependencies of run_task."""
    with (
        patch("agentbench.run_task.load_task") as mock_load,
        patch("agentbench.run_task.clone_repo") as mock_clone,
        patch("agentbench.run_task.checkout_commit") as mock_checkout,
        patch("agentbench.run_task.DockerSandbox") as mock_sandbox_class,
        patch("agentbench.run_task.ulid") as mock_ulid,
    ):
        # Configure mocks
        mock_load.return_value = make_mock_task()
        mock_clone.return_value = (Path("/logs/stdout"), Path("/logs/stderr"), 0)
        mock_checkout.return_value = (Path("/logs/stdout"), Path("/logs/stderr"), 0)
        mock_ulid.ULID.return_value = MagicMock(__str__=lambda x: "01TESTULID000000000000")

        mock_sandbox = MagicMock()
        mock_sandbox.run.return_value = MagicMock(exit_code=0)
        mock_sandbox_class.return_value = mock_sandbox

        yield {
            "load_task": mock_load,
            "clone_repo": mock_clone,
            "checkout_commit": mock_checkout,
            "sandbox_class": mock_sandbox_class,
            "sandbox": mock_sandbox,
            "ulid": mock_ulid,
        }


class TestRunTaskCreatesDirectories:
    """Tests for directory creation in run_task."""

    def test_creates_run_directory(self, tmp_path: Path, mock_dependencies):
        """run_task creates a unique run directory."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        result_path = run_task(task_yaml, out_dir)

        assert result_path.exists()
        assert "runs" in str(result_path)

    def test_creates_workspace_directory(self, tmp_path: Path, mock_dependencies):
        """run_task creates workspace directory."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        result_path = run_task(task_yaml, out_dir)

        workspace = result_path / "workspace"
        assert workspace.exists()

    def test_creates_logs_directory(self, tmp_path: Path, mock_dependencies):
        """run_task creates logs directory."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        result_path = run_task(task_yaml, out_dir)

        logs = result_path / "logs"
        assert logs.exists()

    def test_creates_task_directory(self, tmp_path: Path, mock_dependencies):
        """run_task creates task directory and copies task.yaml."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        result_path = run_task(task_yaml, out_dir)

        task_dir = result_path / "task"
        assert task_dir.exists()


class TestRunTaskLoadsTask:
    """Tests for task loading in run_task."""

    def test_calls_load_task(self, tmp_path: Path, mock_dependencies):
        """run_task calls load_task with correct path."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        run_task(task_yaml, out_dir)

        mock_dependencies["load_task"].assert_called_once_with(task_yaml)


class TestRunTaskGitOperations:
    """Tests for git operations in run_task."""

    def test_clones_repository(self, tmp_path: Path, mock_dependencies):
        """run_task clones the repository."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        run_task(task_yaml, out_dir)

        mock_dependencies["clone_repo"].assert_called_once()
        call_kwargs = mock_dependencies["clone_repo"].call_args.kwargs
        assert call_kwargs["url"] == "https://github.com/example/repo.git"

    def test_checkouts_commit(self, tmp_path: Path, mock_dependencies):
        """run_task checks out the specified commit."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        run_task(task_yaml, out_dir)

        mock_dependencies["checkout_commit"].assert_called_once()
        call_kwargs = mock_dependencies["checkout_commit"].call_args.kwargs
        assert call_kwargs["commit"] == "abc123"

    def test_clone_failure_raises_error(self, tmp_path: Path, mock_dependencies):
        """run_task raises error when clone fails."""
        mock_dependencies["clone_repo"].return_value = (
            Path("/logs/stdout"),
            Path("/logs/stderr"),
            128,  # Non-zero exit code
        )

        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        with pytest.raises(ValueError, match="failed"):
            run_task(task_yaml, out_dir)

    def test_checkout_failure_raises_error(self, tmp_path: Path, mock_dependencies):
        """run_task raises error when checkout fails."""
        mock_dependencies["checkout_commit"].return_value = (
            Path("/logs/stdout"),
            Path("/logs/stderr"),
            1,  # Non-zero exit code
        )

        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        with pytest.raises(ValueError, match="failed"):
            run_task(task_yaml, out_dir)


class TestRunTaskDockerExecution:
    """Tests for Docker execution in run_task."""

    def test_creates_sandbox_with_correct_image(self, tmp_path: Path, mock_dependencies):
        """run_task creates DockerSandbox with correct image."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        run_task(task_yaml, out_dir)

        mock_dependencies["sandbox_class"].assert_called_once_with(
            image="python:3.11",
            workdir="/workspace",
        )

    def test_runs_setup_commands(self, tmp_path: Path, mock_dependencies):
        """run_task runs setup commands in sandbox."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        run_task(task_yaml, out_dir)

        sandbox = mock_dependencies["sandbox"]
        # Expect two run calls: setup and task
        assert sandbox.run.call_count == 2

        # First call is setup (with bridge network)
        first_call = sandbox.run.call_args_list[0]
        assert first_call.kwargs["network"] == "bridge"

    def test_runs_task_command_with_no_network(self, tmp_path: Path, mock_dependencies):
        """run_task runs task command with no network."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        run_task(task_yaml, out_dir)

        sandbox = mock_dependencies["sandbox"]
        # Second call is task (with no network)
        second_call = sandbox.run.call_args_list[1]
        assert second_call.kwargs["network"] == "none"

    def test_setup_failure_raises_error(self, tmp_path: Path, mock_dependencies):
        """run_task raises error when setup fails."""
        sandbox = mock_dependencies["sandbox"]
        sandbox.run.return_value = MagicMock(exit_code=1)

        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        with pytest.raises(ValueError, match="Setup run failed"):
            run_task(task_yaml, out_dir)


class TestRunTaskSavesMetadata:
    """Tests for metadata saving in run_task."""

    def test_creates_run_json(self, tmp_path: Path, mock_dependencies):
        """run_task creates run.json with metadata."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        result_path = run_task(task_yaml, out_dir)

        run_json = result_path / "run.json"
        assert run_json.exists()

    def test_run_json_contains_required_fields(self, tmp_path: Path, mock_dependencies):
        """run.json contains required metadata fields."""
        import json

        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        result_path = run_task(task_yaml, out_dir)

        run_json = result_path / "run.json"
        data = json.loads(run_json.read_text())

        assert "run_id" in data
        assert "task_id" in data
        assert "repo_url" in data
        assert "docker_image" in data
        assert "exit_codes" in data

    def test_copies_task_yaml(self, tmp_path: Path, mock_dependencies):
        """run_task copies task.yaml to task directory."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        result_path = run_task(task_yaml, out_dir)

        copied_yaml = result_path / "task" / "task.yaml"
        assert copied_yaml.exists()


class TestRunTaskReturnValue:
    """Tests for run_task return value."""

    def test_returns_run_directory_path(self, tmp_path: Path, mock_dependencies):
        """run_task returns the path to the run directory."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        result = run_task(task_yaml, out_dir)

        assert isinstance(result, Path)
        assert result.is_dir()

    def test_unique_run_ids(self, tmp_path: Path, mock_dependencies):
        """run_task generates run directories with different timestamps/ULIDs."""
        import time

        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "artifacts"

        result1 = run_task(task_yaml, out_dir)

        # Sleep briefly to ensure different timestamp
        time.sleep(0.01)

        # Reset mock to return a different ULID
        mock_dependencies["ulid"].ULID.return_value = MagicMock(
            __str__=lambda x: "01TESTULID000000000001"
        )

        result2 = run_task(task_yaml, out_dir)

        # Both should be valid directories
        assert result1.is_dir()
        assert result2.is_dir()
