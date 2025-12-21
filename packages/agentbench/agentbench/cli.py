from pathlib import Path

import typer

from agentbench.logging import setup_logging
from agentbench.run_task import run_task
from agentbench.suite_runner import run_suite
from agentbench.tasks.exceptions import SuiteNotFoundError
from agentbench.tasks.loader import load_suite

app = typer.Typer(no_args_is_help=True)

# Initialize logging when the CLI module is loaded
setup_logging()


@app.command("run-task")
def run_task_cmd(
    task: Path = typer.Argument(
        ...,
        help="Path to the task YAML file",
    ),
    out: Path = typer.Option(
        Path("artifacts"),
        "--out",
        "-o",
        help="Output directory for artifacts",
    ),
):
    """
    Execute a task defined in a YAML file.

    This command runs a task inside a Docker container, captures all output,
    and stores the results in an artifact directory with a unique run ID.
    """
    path = run_task(task, out)
    typer.echo(f"Run completed. Artifacts saved to: {path}")


@app.command("validate-suite")
def validate_suite_cmd(
    suite: str = typer.Argument(..., help="Suite name (e.g., custom-dev)"),
    tasks_root: Path = typer.Option(
        Path("tasks"),
        "--tasks",
        "-t",
        help="Root directory containing task suites",
    ),
    out: Path = typer.Option(
        Path("artifacts"), "--out", "-o", help="Output directory for artifacts"
    ),
):
    """
    Validate all tasks in a suite.

    Runs baseline validation on each task to ensure tests fail as expected.
    Tasks where tests pass are marked as invalid.
    """
    try:
        runs_dir = run_suite(
            suite_name=suite, tasks_root=tasks_root, out_dir=out
        )

        if runs_dir is None:
            # Empty suite - warning already printed by run_suite
            raise typer.Exit(code=0)

        typer.echo(f"Validated suite {suite}: {runs_dir}")
    except SuiteNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@app.command("list-tasks")
def list_tasks_cmd(
    suite: str = typer.Argument(..., help="Suite name"),
    tasks_root: Path = typer.Option(Path("tasks"), "--tasks", "-t"),
):
    """List all tasks in a suite."""
    try:
        tasks = load_suite(tasks_root=tasks_root, suite_name=suite)

        if not tasks:
            typer.echo(f"Warning: No tasks found in suite '{suite}'")
            raise typer.Exit(code=0)

        typer.echo(f"{len(tasks)} found in {suite}")

        for i, task in enumerate(tasks):
            typer.echo(f" Task{i + 1}: {task.id}")
    except SuiteNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@app.callback()
def main():
    """
    AgentBench: A framework for running and evaluating AI agents.

    Run tasks in isolated Docker containers and capture results.
    """
    pass
