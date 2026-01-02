import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agentbench.agent_runner import run_agent_attempt
from agentbench.agents.base import AgentResult
from agentbench.logging import setup_logging
from agentbench.run_task import run_task
from agentbench.schemas.attempt_record import AttemptRecord
from agentbench.suite_runner import run_suite
from agentbench.tasks.exceptions import SuiteNotFoundError
from agentbench.tasks.loader import load_suite, load_task

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)
console = Console()

setup_logging()


def print_agent_summary(record: AttemptRecord) -> None:
    """Print a pretty summary table for an agent run."""
    table = Table(title="Agent Run Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Run ID", record.run_id)
    table.add_row("Task ID", record.task_id)
    table.add_row("Success", "✓" if record.result.passed else "✗")
    table.add_row("Exit Code", str(record.result.exit_code))
    table.add_row("Duration", f"{record.duration_sec:.1f}s")
    table.add_row("Variant", record.variant or "baseline")
    
    if record.result.failure_reason:
        table.add_row("Failure Reason", str(record.result.failure_reason))
    
    console.print(table)


@app.command("run-task")
def run_task_cmd(
    task: Path | None = typer.Argument(
        None,
        help="Path to the task YAML file (positional)",
    ),
    task_opt: Path | None = typer.Option(
        None,
        "--task",
        "-t",
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
    if task is not None and task_opt is not None:
        raise typer.BadParameter("Use either TASK or --task, not both.")
    task_path = task_opt or task
    if task_path is None:
        raise typer.BadParameter("Missing task path. Provide TASK or --task.")

    logger.info("Running task from %s", task_path)
    path = run_task(task_path, out)
    logger.info("Task completed, artifacts saved to %s", path)
    typer.echo(f"Run completed. Artifacts saved to: {path}")


@app.command("run-agent")
def run_agent_cmd(
    task_path: Path = typer.Option(
        ...,
        "--task",
        "-t",
        help="Path to the task YAML file",
    ),
    variant: str = typer.Option(
        "scripted",
        "--variant",
        "-v",
        help="Agent variant to use (e.g., scripted)",
    ),
    out_dir: Path = typer.Option(
        Path("artifacts"),
        "--out",
        "-o",
        help="Output directory for artifacts",
    ),
):
    """
    Run an agent on a single task.
    
    This command loads a task, runs the specified agent variant,
    and produces an attempt record with all artifacts.
    """
    try:
        logger.info("Loading task from %s", task_path)
        task = load_task(task_path)
        
        workspace_dir = out_dir / "workspace" / task.id
        artifacts_dir = out_dir / "agent_runs" / task.id
        
        workspace_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        console.print(f"[bold blue]Running agent '{variant}' on task '{task.id}'...[/bold blue]")
        
        record = run_agent_attempt(
            task=task,
            workspace_dir=workspace_dir,
            artifacts_dir=artifacts_dir,
        )
        
        print_agent_summary(record)
        
        console.print(f"\n[dim]Artifacts saved to: {artifacts_dir}[/dim]")
        
        if not record.result.passed:
            raise typer.Exit(code=1)
            
    except FileNotFoundError as e:
        logger.error("Task file not found: %s", task_path)
        console.print(f"[red]Error: Task file not found: {task_path}[/red]")
        raise typer.Exit(code=1) from None
    except Exception as e:
        logger.exception("Error running agent: %s", e)
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from None


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
    include_flaky: bool = typer.Option(
        False,
        "--include-flaky",
        help="Include tasks labeled 'flaky' (skipped by default)",
    ),
):
    """
    Validate all tasks in a suite.

    Runs baseline validation on each task to ensure tests fail as expected.
    Tasks where tests pass are marked as invalid.
    """
    try:
        logger.info("Validating suite %s", suite)
        skip_labels = set() if include_flaky else {"flaky"}
        runs_dir = run_suite(
            suite_name=suite,
            tasks_root=tasks_root,
            out_dir=out,
            skip_labels=skip_labels,
        )

        if runs_dir is None:
            raise typer.Exit(code=0)

        typer.echo(f"Validated suite {suite}: {runs_dir}")
    except SuiteNotFoundError as e:
        logger.error("Suite not found: %s", suite)
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
        logger.error("Suite not found: %s", suite)
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

@app.callback()
def main():
    """
    AgentBench: A framework for running and evaluating AI agents.

    Run tasks in isolated Docker containers and capture results.
    """
    pass
