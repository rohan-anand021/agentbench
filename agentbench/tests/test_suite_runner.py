"""Unit tests for suite_runner module.

Tests the run_suite function with mocked dependencies.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbench.suite_runner import SuiteInterrupted, run_suite


def make_mock_task(task_id: str = "test-task-1"):
    """Create a mock TaskSpec."""
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.suite = "test-suite"
    mock_task.repo.url = "https://github.com/example/repo.git"
    mock_task.repo.commit = "abc123"
    mock_task.environment.docker_image = "python:3.11"
    mock_task.environment.workdir = "/workspace"
    mock_task.environment.timeout_sec = 300
    mock_task.setup.commands = ["pip install -e ."]
    mock_task.run.command = "pytest tests/"
    return mock_task


def make_mock_validation_result(task_id: str, valid: bool):
    """Create a mock ValidationResult."""
    result = MagicMock()
    result.valid = valid
    result.task_id = task_id
    result.error_reason = None if valid else "baseline_not_failing"
    result.model_dump = MagicMock(
        return_value={
            "task_id": task_id,
            "valid": valid,
            "error_reason": result.error_reason,
        }
    )
    return result


@pytest.fixture
def mock_dependencies():
    """Patch all external dependencies of run_suite."""
    with (
        patch("agentbench.suite_runner.load_suite") as mock_load,
        patch("agentbench.suite_runner.validate_baseline") as mock_validate,
        patch("agentbench.suite_runner.console") as mock_console,
        patch("agentbench.suite_runner.ulid") as mock_ulid,
        patch("agentbench.suite_runner.Progress") as mock_progress_class,
    ):
        mock_console.print = MagicMock()
        mock_ulid.ULID.return_value = MagicMock(__str__=lambda x: "01TESTULID000000000000")

        # Mock Progress context manager properly
        mock_progress = MagicMock()
        mock_progress.add_task.return_value = 0
        mock_progress_class.return_value.__enter__ = MagicMock(return_value=mock_progress)
        mock_progress_class.return_value.__exit__ = MagicMock(return_value=False)

        yield {
            "load_suite": mock_load,
            "validate_baseline": mock_validate,
            "console": mock_console,
            "ulid": mock_ulid,
            "progress": mock_progress,
        }


class TestRunSuiteLoading:
    """Tests for suite loading in run_suite."""

    def test_calls_load_suite(self, tmp_path: Path, mock_dependencies):
        """run_suite calls load_suite with correct arguments."""
        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        mock_dependencies["load_suite"].return_value = [make_mock_task()]
        mock_dependencies["validate_baseline"].return_value = (
            make_mock_validation_result("test-task-1", True)
        )

        run_suite("test-suite", tasks_root, out_dir)

        mock_dependencies["load_suite"].assert_called_once_with(
            tasks_root=tasks_root,
            suite_name="test-suite",
        )


class TestRunSuiteEmptySuite:
    """Tests for empty suite handling."""

    def test_returns_none_for_empty_suite(self, tmp_path: Path, mock_dependencies):
        """run_suite returns None for empty suite."""
        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        mock_dependencies["load_suite"].return_value = []

        result = run_suite("empty-suite", tasks_root, out_dir)

        assert result is None

    def test_prints_warning_for_empty_suite(self, tmp_path: Path, mock_dependencies):
        """run_suite prints warning for empty suite."""
        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        mock_dependencies["load_suite"].return_value = []

        run_suite("empty-suite", tasks_root, out_dir)

        # Check that console.print was called with warning
        calls = mock_dependencies["console"].print.call_args_list
        warning_printed = any("No tasks found" in str(call) for call in calls)
        assert warning_printed


class TestRunSuiteValidation:
    """Tests for task validation in run_suite."""

    def test_validates_each_task(self, tmp_path: Path, mock_dependencies):
        """run_suite calls validate_baseline for each task."""
        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        tasks = [make_mock_task(f"task-{i}") for i in range(3)]
        mock_dependencies["load_suite"].return_value = tasks
        mock_dependencies["validate_baseline"].return_value = (
            make_mock_validation_result("task", True)
        )

        run_suite("test-suite", tasks_root, out_dir)

        assert mock_dependencies["validate_baseline"].call_count == 3

    def test_counts_valid_tasks(self, tmp_path: Path, mock_dependencies):
        """run_suite correctly counts valid tasks."""
        import json

        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        tasks = [make_mock_task(f"task-{i}") for i in range(3)]
        mock_dependencies["load_suite"].return_value = tasks
        mock_dependencies["validate_baseline"].side_effect = [
            make_mock_validation_result("task-0", True),
            make_mock_validation_result("task-1", True),
            make_mock_validation_result("task-2", False),
        ]

        result_path = run_suite("test-suite", tasks_root, out_dir)

        run_json = result_path / "run.json"
        data = json.loads(run_json.read_text())

        assert data["valid_count"] == 2
        assert data["invalid_count"] == 1


class TestRunSuiteOutput:
    """Tests for run_suite output files."""

    def test_creates_run_directory(self, tmp_path: Path, mock_dependencies):
        """run_suite creates a unique run directory."""
        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        mock_dependencies["load_suite"].return_value = [make_mock_task()]
        mock_dependencies["validate_baseline"].return_value = (
            make_mock_validation_result("test-task-1", True)
        )

        result_path = run_suite("test-suite", tasks_root, out_dir)

        assert result_path.exists()
        assert "test-suite" in result_path.name
        assert "baseline" in result_path.name

    def test_creates_run_json(self, tmp_path: Path, mock_dependencies):
        """run_suite creates run.json metadata file."""
        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        mock_dependencies["load_suite"].return_value = [make_mock_task()]
        mock_dependencies["validate_baseline"].return_value = (
            make_mock_validation_result("test-task-1", True)
        )

        result_path = run_suite("test-suite", tasks_root, out_dir)

        run_json = result_path / "run.json"
        assert run_json.exists()

    def test_run_json_contains_required_fields(self, tmp_path: Path, mock_dependencies):
        """run.json contains required metadata fields."""
        import json

        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        mock_dependencies["load_suite"].return_value = [make_mock_task()]
        mock_dependencies["validate_baseline"].return_value = (
            make_mock_validation_result("test-task-1", True)
        )

        result_path = run_suite("test-suite", tasks_root, out_dir)

        run_json = result_path / "run.json"
        data = json.loads(run_json.read_text())

        assert "run_id" in data
        assert "suite" in data
        assert "started_at" in data
        assert "ended_at" in data
        assert "task_count" in data
        assert "valid_count" in data
        assert "invalid_count" in data

    def test_creates_attempts_jsonl(self, tmp_path: Path, mock_dependencies):
        """run_suite creates attempts.jsonl file."""
        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        mock_dependencies["load_suite"].return_value = [make_mock_task()]
        mock_dependencies["validate_baseline"].return_value = (
            make_mock_validation_result("test-task-1", True)
        )

        result_path = run_suite("test-suite", tasks_root, out_dir)

        attempts_jsonl = result_path / "logs" / "attempts.jsonl"
        assert attempts_jsonl.exists()


class TestRunSuiteErrorHandling:
    """Tests for error handling in run_suite."""

    def test_continues_after_task_failure(self, tmp_path: Path, mock_dependencies):
        """run_suite continues processing after a task fails."""
        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        tasks = [make_mock_task(f"task-{i}") for i in range(3)]
        mock_dependencies["load_suite"].return_value = tasks

        # Second task raises an exception
        mock_dependencies["validate_baseline"].side_effect = [
            make_mock_validation_result("task-0", True),
            RuntimeError("Task failed"),
            make_mock_validation_result("task-2", True),
        ]

        result_path = run_suite("test-suite", tasks_root, out_dir)

        # Should have processed all 3 tasks
        assert mock_dependencies["validate_baseline"].call_count == 3

        # Should record 1 invalid (error) task
        import json

        run_json = result_path / "run.json"
        data = json.loads(run_json.read_text())
        assert data["valid_count"] == 2
        assert data["invalid_count"] == 1


class TestRunSuiteWorkspaces:
    """Tests for workspace creation in run_suite."""

    def test_creates_task_workspace_directories(self, tmp_path: Path, mock_dependencies):
        """run_suite creates workspace directory for each task."""
        tasks_root = tmp_path / "tasks"
        tasks_root.mkdir()
        out_dir = tmp_path / "artifacts"

        tasks = [make_mock_task("task-1"), make_mock_task("task-2")]
        mock_dependencies["load_suite"].return_value = tasks
        mock_dependencies["validate_baseline"].return_value = (
            make_mock_validation_result("task", True)
        )

        result_path = run_suite("test-suite", tasks_root, out_dir)

        workspace_dir = result_path / "workspace"
        assert workspace_dir.exists()
        assert (workspace_dir / "task-1").exists()
        assert (workspace_dir / "task-2").exists()


class TestSuiteInterrupted:
    """Tests for SuiteInterrupted exception."""

    def test_suite_interrupted_is_exception(self):
        """SuiteInterrupted is an Exception."""
        assert issubclass(SuiteInterrupted, Exception)

    def test_suite_interrupted_can_be_raised(self):
        """SuiteInterrupted can be raised and caught."""
        with pytest.raises(SuiteInterrupted):
            raise SuiteInterrupted()
