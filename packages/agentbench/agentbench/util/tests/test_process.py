"""Unit tests for process utilities."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbench.util.process import check_exit_code, run_command


class TestRunCommand:
    """Tests for run_command function."""

    def test_run_command_creates_output_files(self, tmp_path: Path):
        """run_command creates stdout and stderr files."""
        logs_dir = tmp_path / "logs"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            stdout_path, stderr_path, exit_code = run_command(
                cmd_name="test_cmd",
                cmd=["echo", "hello"],
                timeout=30,
                logs_dir=logs_dir,
            )

            assert stdout_path.exists()
            assert stderr_path.exists()
            assert stdout_path.name == "test_cmd_stdout.txt"
            assert stderr_path.name == "test_cmd_stderr.txt"

    def test_run_command_returns_exit_code_on_success(self, tmp_path: Path):
        """run_command returns exit code 0 on success."""
        logs_dir = tmp_path / "logs"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _, _, exit_code = run_command(
                cmd_name="test_cmd",
                cmd=["echo", "hello"],
                timeout=30,
                logs_dir=logs_dir,
            )

            assert exit_code == 0

    def test_run_command_returns_exit_code_on_failure(self, tmp_path: Path):
        """run_command returns non-zero exit code on failure."""
        logs_dir = tmp_path / "logs"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            _, _, exit_code = run_command(
                cmd_name="test_cmd",
                cmd=["false"],
                timeout=30,
                logs_dir=logs_dir,
            )

            assert exit_code == 1

    def test_run_command_timeout_returns_124(self, tmp_path: Path):
        """run_command returns exit code 124 on timeout."""
        logs_dir = tmp_path / "logs"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)
            _, stderr_path, exit_code = run_command(
                cmd_name="test_cmd",
                cmd=["sleep", "100"],
                timeout=30,
                logs_dir=logs_dir,
            )

            assert exit_code == 124
            assert "timed out" in stderr_path.read_text()

    def test_run_command_creates_logs_dir_if_missing(self, tmp_path: Path):
        """run_command creates logs directory if it doesn't exist."""
        logs_dir = tmp_path / "nested" / "logs"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_command(
                cmd_name="test_cmd",
                cmd=["echo", "hello"],
                timeout=30,
                logs_dir=logs_dir,
            )

            assert logs_dir.exists()

    def test_run_command_with_cwd(self, tmp_path: Path):
        """run_command passes cwd to subprocess."""
        logs_dir = tmp_path / "logs"
        cwd = tmp_path / "workdir"
        cwd.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_command(
                cmd_name="test_cmd",
                cmd=["pwd"],
                timeout=30,
                logs_dir=logs_dir,
                cwd=cwd,
            )

            call_args = mock_run.call_args
            assert call_args.kwargs.get("cwd") == cwd

    def test_run_command_respects_timeout(self, tmp_path: Path):
        """run_command passes timeout to subprocess."""
        logs_dir = tmp_path / "logs"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_command(
                cmd_name="test_cmd",
                cmd=["echo", "hello"],
                timeout=60,
                logs_dir=logs_dir,
            )

            call_args = mock_run.call_args
            assert call_args.kwargs.get("timeout") == 60


class TestCheckExitCode:
    """Tests for check_exit_code function."""

    def test_check_exit_code_success_returns_none(self):
        """check_exit_code returns None for success (exit code 0)."""
        result = check_exit_code("test_cmd", exit_code=0)
        assert result is None

    def test_check_exit_code_failure_returns_exception(self):
        """check_exit_code returns Exception for non-zero exit code."""
        result = check_exit_code("test_cmd", exit_code=1)
        assert isinstance(result, ValueError)
        assert "test_cmd" in str(result)
        assert "failed" in str(result)

    def test_check_exit_code_custom_success_code(self):
        """check_exit_code accepts custom success code."""
        # Exit code 1 is success for this command
        result = check_exit_code("test_cmd", exit_code=1, success=1)
        assert result is None

    def test_check_exit_code_custom_success_code_failure(self):
        """check_exit_code fails when exit code doesn't match custom success."""
        result = check_exit_code("test_cmd", exit_code=0, success=1)
        assert isinstance(result, ValueError)

    def test_check_exit_code_timeout_exit_code(self):
        """check_exit_code returns error for timeout exit code (124)."""
        result = check_exit_code("test_cmd", exit_code=124)
        assert isinstance(result, ValueError)

    def test_check_exit_code_includes_cmd_name_in_error(self):
        """check_exit_code includes command name in error message."""
        result = check_exit_code("git_clone", exit_code=128)
        assert "git_clone" in str(result)
