"""Unit tests for git utilities."""

from pathlib import Path
from unittest.mock import patch

from agentbench.util.git import checkout_commit, clone_repo


class TestCloneRepo:
    """Tests for clone_repo function."""

    def test_clone_repo_calls_git_clone(self, tmp_path: Path):
        """clone_repo runs git clone command."""
        logs_dir = tmp_path / "logs"
        dest = tmp_path / "repo"

        with patch("agentbench.util.git.run_command") as mock_run:
            mock_run.return_value = (
                logs_dir / "git_clone_stdout.txt",
                logs_dir / "git_clone_stderr.txt",
                0,
            )

            stdout, stderr, exit_code = clone_repo(
                url="https://github.com/example/repo.git",
                dest=dest,
                logs_dir=logs_dir,
            )

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            cmd = call_args.kwargs.get("cmd")

            assert cmd[0] == "git"
            assert cmd[1] == "clone"
            assert "https://github.com/example/repo.git" in cmd
            assert str(dest) in cmd

    def test_clone_repo_returns_output_paths(self, tmp_path: Path):
        """clone_repo returns stdout, stderr paths and exit code."""
        logs_dir = tmp_path / "logs"
        dest = tmp_path / "repo"

        with patch("agentbench.util.git.run_command") as mock_run:
            expected_stdout = logs_dir / "git_clone_stdout.txt"
            expected_stderr = logs_dir / "git_clone_stderr.txt"
            mock_run.return_value = (expected_stdout, expected_stderr, 0)

            stdout, stderr, exit_code = clone_repo(
                url="https://github.com/example/repo.git",
                dest=dest,
                logs_dir=logs_dir,
            )

            assert stdout == expected_stdout
            assert stderr == expected_stderr
            assert exit_code == 0

    def test_clone_repo_uses_default_timeout(self, tmp_path: Path):
        """clone_repo uses default timeout of 120 seconds."""
        logs_dir = tmp_path / "logs"
        dest = tmp_path / "repo"

        with patch("agentbench.util.git.run_command") as mock_run:
            mock_run.return_value = (Path(), Path(), 0)

            clone_repo(
                url="https://github.com/example/repo.git",
                dest=dest,
                logs_dir=logs_dir,
            )

            call_args = mock_run.call_args
            assert call_args.kwargs.get("timeout") == 120

    def test_clone_repo_accepts_custom_timeout(self, tmp_path: Path):
        """clone_repo accepts custom timeout."""
        logs_dir = tmp_path / "logs"
        dest = tmp_path / "repo"

        with patch("agentbench.util.git.run_command") as mock_run:
            mock_run.return_value = (Path(), Path(), 0)

            clone_repo(
                url="https://github.com/example/repo.git",
                dest=dest,
                logs_dir=logs_dir,
                timeout_sec=300,
            )

            call_args = mock_run.call_args
            assert call_args.kwargs.get("timeout") == 300

    def test_clone_repo_returns_nonzero_on_failure(self, tmp_path: Path):
        """clone_repo returns non-zero exit code on failure."""
        logs_dir = tmp_path / "logs"
        dest = tmp_path / "repo"

        with patch("agentbench.util.git.run_command") as mock_run:
            mock_run.return_value = (Path(), Path(), 128)

            _, _, exit_code = clone_repo(
                url="https://github.com/nonexistent/repo.git",
                dest=dest,
                logs_dir=logs_dir,
            )

            assert exit_code == 128


class TestCheckoutCommit:
    """Tests for checkout_commit function."""

    def test_checkout_commit_calls_git_checkout(self, tmp_path: Path):
        """checkout_commit runs git checkout command."""
        logs_dir = tmp_path / "logs"
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        with patch("agentbench.util.git.run_command") as mock_run:
            mock_run.return_value = (Path(), Path(), 0)

            checkout_commit(
                repo_dir=repo_dir,
                commit="abc123",
                logs_dir=logs_dir,
            )

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            cmd = call_args.kwargs.get("cmd")

            assert cmd[0] == "git"
            assert cmd[1] == "checkout"
            assert "abc123" in cmd

    def test_checkout_commit_runs_in_repo_dir(self, tmp_path: Path):
        """checkout_commit runs in the correct repository directory."""
        logs_dir = tmp_path / "logs"
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        with patch("agentbench.util.git.run_command") as mock_run:
            mock_run.return_value = (Path(), Path(), 0)

            checkout_commit(
                repo_dir=repo_dir,
                commit="abc123",
                logs_dir=logs_dir,
            )

            call_args = mock_run.call_args
            assert call_args.kwargs.get("cwd") == repo_dir

    def test_checkout_commit_returns_output_paths(self, tmp_path: Path):
        """checkout_commit returns stdout, stderr paths and exit code."""
        logs_dir = tmp_path / "logs"
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        with patch("agentbench.util.git.run_command") as mock_run:
            expected_stdout = logs_dir / "git_checkout_stdout.txt"
            expected_stderr = logs_dir / "git_checkout_stderr.txt"
            mock_run.return_value = (expected_stdout, expected_stderr, 0)

            stdout, stderr, exit_code = checkout_commit(
                repo_dir=repo_dir,
                commit="abc123",
                logs_dir=logs_dir,
            )

            assert stdout == expected_stdout
            assert stderr == expected_stderr
            assert exit_code == 0

    def test_checkout_commit_uses_default_timeout(self, tmp_path: Path):
        """checkout_commit uses default timeout of 120 seconds."""
        logs_dir = tmp_path / "logs"
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        with patch("agentbench.util.git.run_command") as mock_run:
            mock_run.return_value = (Path(), Path(), 0)

            checkout_commit(
                repo_dir=repo_dir,
                commit="abc123",
                logs_dir=logs_dir,
            )

            call_args = mock_run.call_args
            assert call_args.kwargs.get("timeout") == 120

    def test_checkout_commit_returns_nonzero_for_invalid_commit(self, tmp_path: Path):
        """checkout_commit returns non-zero for invalid commit."""
        logs_dir = tmp_path / "logs"
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        with patch("agentbench.util.git.run_command") as mock_run:
            mock_run.return_value = (Path(), Path(), 1)

            _, _, exit_code = checkout_commit(
                repo_dir=repo_dir,
                commit="invalidcommit",
                logs_dir=logs_dir,
            )

            assert exit_code == 1
