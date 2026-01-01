"""Unit tests for CLI commands using typer.testing.CliRunner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agentbench.cli import app

runner = CliRunner()


class TestRunTaskCommand:
    """Tests for the run-task CLI command."""

    def test_run_task_command_exists(self):
        """run-task command is registered."""
        result = runner.invoke(app, ["run-task", "--help"])
        assert result.exit_code == 0
        assert "Execute a task" in result.output

    def test_run_task_requires_task_argument(self):
        """run-task requires task path argument."""
        result = runner.invoke(app, ["run-task"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_run_task_default_output_dir(self):
        """run-task uses 'artifacts' as default output directory."""
        result = runner.invoke(app, ["run-task", "--help"])
        assert "artifacts" in result.output

    @patch("agentbench.cli.run_task")
    def test_run_task_calls_run_task_function(self, mock_run_task, tmp_path: Path):
        """run-task calls the run_task function with correct arguments."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        mock_run_task.return_value = tmp_path / "runs" / "run_001"

        result = runner.invoke(app, ["run-task", str(task_yaml)])

        assert result.exit_code == 0
        mock_run_task.assert_called_once()

    @patch("agentbench.cli.run_task")
    def test_run_task_custom_output_dir(self, mock_run_task, tmp_path: Path):
        """run-task accepts custom output directory."""
        task_yaml = tmp_path / "task.yaml"
        task_yaml.write_text("id: test")
        out_dir = tmp_path / "custom_output"
        mock_run_task.return_value = out_dir / "runs" / "run_001"

        result = runner.invoke(
            app, ["run-task", str(task_yaml), "--out", str(out_dir)]
        )

        assert result.exit_code == 0
        call_args = mock_run_task.call_args
        # Second argument should be the out_dir
        assert call_args[0][1] == out_dir


class TestValidateSuiteCommand:
    """Tests for the validate-suite CLI command."""

    def test_validate_suite_command_exists(self):
        """validate-suite command is registered."""
        result = runner.invoke(app, ["validate-suite", "--help"])
        assert result.exit_code == 0
        assert "Validate all tasks" in result.output

    def test_validate_suite_requires_suite_argument(self):
        """validate-suite requires suite name argument."""
        result = runner.invoke(app, ["validate-suite"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    @patch("agentbench.cli.run_suite")
    def test_validate_suite_calls_run_suite(self, mock_run_suite, tmp_path: Path):
        """validate-suite calls run_suite function."""
        mock_run_suite.return_value = tmp_path / "runs" / "run_001"

        result = runner.invoke(
            app,
            ["validate-suite", "custom-dev", "--tasks", str(tmp_path)],
        )

        assert result.exit_code == 0
        mock_run_suite.assert_called_once()

    @patch("agentbench.cli.run_suite")
    def test_validate_suite_handles_empty_suite(self, mock_run_suite, tmp_path: Path):
        """validate-suite handles empty suite (returns None)."""
        mock_run_suite.return_value = None

        result = runner.invoke(
            app,
            ["validate-suite", "empty-suite", "--tasks", str(tmp_path)],
        )

        # Empty suite should exit with 0
        assert result.exit_code == 0

    @patch("agentbench.cli.run_suite")
    def test_validate_suite_handles_not_found(self, mock_run_suite, tmp_path: Path):
        """validate-suite handles SuiteNotFoundError."""
        from agentbench.tasks.exceptions import SuiteNotFoundError

        mock_run_suite.side_effect = SuiteNotFoundError("nonexistent")

        result = runner.invoke(
            app,
            ["validate-suite", "nonexistent", "--tasks", str(tmp_path)],
        )

        assert result.exit_code == 1
        assert "Error" in result.output


class TestListTasksCommand:
    """Tests for the list-tasks CLI command."""

    def test_list_tasks_command_exists(self):
        """list-tasks command is registered."""
        result = runner.invoke(app, ["list-tasks", "--help"])
        assert result.exit_code == 0
        assert "List all tasks" in result.output

    def test_list_tasks_requires_suite_argument(self):
        """list-tasks requires suite name argument."""
        result = runner.invoke(app, ["list-tasks"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    @patch("agentbench.cli.load_suite")
    def test_list_tasks_shows_task_count(self, mock_load_suite, tmp_path: Path):
        """list-tasks shows number of tasks found."""
        mock_task1 = MagicMock()
        mock_task1.id = "task1"
        mock_task2 = MagicMock()
        mock_task2.id = "task2"
        mock_load_suite.return_value = [mock_task1, mock_task2]

        result = runner.invoke(
            app,
            ["list-tasks", "test-suite", "--tasks", str(tmp_path)],
        )

        assert result.exit_code == 0
        assert "2 found" in result.output
        assert "task1" in result.output
        assert "task2" in result.output

    @patch("agentbench.cli.load_suite")
    def test_list_tasks_empty_suite(self, mock_load_suite, tmp_path: Path):
        """list-tasks warns about empty suite."""
        mock_load_suite.return_value = []

        result = runner.invoke(
            app,
            ["list-tasks", "empty-suite", "--tasks", str(tmp_path)],
        )

        assert result.exit_code == 0
        assert "Warning" in result.output
        assert "No tasks found" in result.output

    @patch("agentbench.cli.load_suite")
    def test_list_tasks_handles_not_found(self, mock_load_suite, tmp_path: Path):
        """list-tasks handles SuiteNotFoundError."""
        from agentbench.tasks.exceptions import SuiteNotFoundError

        mock_load_suite.side_effect = SuiteNotFoundError("nonexistent")

        result = runner.invoke(
            app,
            ["list-tasks", "nonexistent", "--tasks", str(tmp_path)],
        )

        assert result.exit_code == 1
        assert "Error" in result.output


class TestMainCallback:
    """Tests for the main CLI callback."""

    def test_no_args_shows_help(self):
        """No arguments shows help message."""
        result = runner.invoke(app, [])
        # With no_args_is_help=True, typer shows help but may exit 2 or 0
        # The important thing is help content is shown
        assert "AgentBench" in result.output
        assert "run-task" in result.output
        assert "validate-suite" in result.output
        assert "list-tasks" in result.output

    def test_help_flag(self):
        """--help flag shows help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "AgentBench" in result.stdout
