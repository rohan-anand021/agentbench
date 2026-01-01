"""Tests for AttemptContext crash safety and edge cases."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbench.scoring.taxonomy import FailureReason
from agentbench.util.attempt import AttemptContext
from agentbench.util.jsonl import read_jsonl


def create_mock_task(task_id: str = "test-task-1", suite: str = "test-suite"):
    """Create a minimal mock TaskSpec for testing."""
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.suite = suite
    mock_task.environment.timeout_sec = 300
    return mock_task


class TestAttemptContextCrashSafety:
    """Test that AttemptContext correctly records attempts even during failures."""

    def test_normal_completion_writes_record(self, tmp_path: Path):
        """Verify that normal completion produces a valid JSONL record."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        mock_task = create_mock_task()

        with AttemptContext(mock_task, logs_dir, "baseline") as attempt:
            attempt.mark_stage("test_stage")
            attempt.set_exit_code(0)
            attempt.valid = True

        attempts_file = tmp_path / "attempts.jsonl"
        records = list(read_jsonl(attempts_file))

        assert len(records) == 1
        assert records[0]["task_id"] == "test-task-1"
        assert records[0]["result"]["passed"] is True
        assert records[0]["variant"] == "baseline"

    def test_forced_exception_still_writes_record(self, tmp_path: Path):
        """Verify that a forced exception still produces a valid JSONL record."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        mock_task = create_mock_task()

        with pytest.raises(RuntimeError):
            with AttemptContext(mock_task, logs_dir, "baseline") as attempt:
                attempt.mark_stage("failing_stage")
                raise RuntimeError("Simulated crash")

        attempts_file = tmp_path / "attempts.jsonl"
        records = list(read_jsonl(attempts_file))

        assert len(records) == 1
        assert records[0]["result"]["failure_reason"] == "UNKNOWN"
        assert records[0]["baseline_validation"]["attempted"] is True

    def test_keyboard_interrupt_writes_interrupted_reason(self, tmp_path: Path):
        """Verify that KeyboardInterrupt produces record with INTERRUPTED reason."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        mock_task = create_mock_task()

        with pytest.raises(KeyboardInterrupt):
            with AttemptContext(mock_task, logs_dir, "baseline") as attempt:
                attempt.mark_stage("interrupted_stage")
                raise KeyboardInterrupt("User cancelled")

        attempts_file = tmp_path / "attempts.jsonl"
        records = list(read_jsonl(attempts_file))

        assert len(records) == 1
        assert records[0]["result"]["failure_reason"] == "INTERRUPTED"

    def test_explicit_failure_reason_preserved(self, tmp_path: Path):
        """Verify that explicitly set failure reason is not overwritten."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        mock_task = create_mock_task()

        with pytest.raises(RuntimeError):
            with AttemptContext(mock_task, logs_dir, "baseline") as attempt:
                attempt.mark_stage("setup")
                attempt.set_failure_reason(FailureReason.SETUP_FAILED)
                raise RuntimeError("Setup failed")

        attempts_file = tmp_path / "attempts.jsonl"
        records = list(read_jsonl(attempts_file))

        assert len(records) == 1
        assert records[0]["result"]["failure_reason"] == "SETUP_FAILED"

    def test_partial_artifacts_recorded(self, tmp_path: Path):
        """Verify that partial artifacts are recorded when failure occurs mid-execution."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        mock_task = create_mock_task()

        with pytest.raises(RuntimeError):
            with AttemptContext(mock_task, logs_dir, "baseline") as attempt:
                attempt.mark_stage("git_clone")
                attempt.add_artifact(
                    "clone_stdout", "/path/to/clone_stdout.txt"
                )
                attempt.add_artifact(
                    "clone_stderr", "/path/to/clone_stderr.txt"
                )
                # Simulate failure before adding more artifacts
                raise RuntimeError("Clone failed")

        attempts_file = tmp_path / "attempts.jsonl"
        records = list(read_jsonl(attempts_file))

        assert len(records) == 1
        assert "clone_stdout" in records[0]["artifact_paths"]
        assert "clone_stderr" in records[0]["artifact_paths"]
        # Later artifacts should not be present
        assert "setup_stdout" not in records[0]["artifact_paths"]

    def test_multiple_attempts_append_to_file(self, tmp_path: Path):
        """Verify that multiple attempts are appended to the same file."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        mock_task = create_mock_task()

        # First attempt - success
        with AttemptContext(mock_task, logs_dir, "baseline") as attempt:
            attempt.valid = True

        # Second attempt - failure
        with pytest.raises(RuntimeError):
            with AttemptContext(mock_task, logs_dir, "baseline") as attempt:
                raise RuntimeError("Second attempt failed")

        attempts_file = tmp_path / "attempts.jsonl"
        records = list(read_jsonl(attempts_file))

        assert len(records) == 2
        assert records[0]["result"]["passed"] is True
        assert records[1]["result"]["failure_reason"] == "UNKNOWN"


class TestAppendJsonlDiskFull:
    """Test disk full handling in append_jsonl."""

    def test_disk_full_returns_false(self, tmp_path: Path):
        """Verify that disk full error returns False instead of crashing."""
        from agentbench.util.jsonl import append_jsonl

        test_file = tmp_path / "test.jsonl"

        with patch(
            "builtins.open", side_effect=OSError("No space left on device")
        ):
            with patch(
                "tempfile.NamedTemporaryFile",
                side_effect=OSError("No space left on device"),
            ):
                result = append_jsonl(test_file, {"test": "data"})

        assert result is False

    def test_successful_write_returns_true(self, tmp_path: Path):
        """Verify that successful write returns True."""
        from agentbench.util.jsonl import append_jsonl

        test_file = tmp_path / "test.jsonl"
        result = append_jsonl(test_file, {"test": "data"})

        assert result is True
        assert test_file.exists()
