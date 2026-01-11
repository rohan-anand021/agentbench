import logging
import os
import shutil
from pathlib import Path

import typer
from pydantic import SecretStr
from rich.console import Console
from rich.table import Table

from agentbench.agent_runner import run_agent_attempt
from agentbench.llm.config import LLMConfig, LLMProvider, ProviderConfig
from agentbench.llm.openrouter import OpenRouterClient
from agentbench.logging import setup_logging
from agentbench.run_task import run_task
from agentbench.reporting.cli import report_app
from agentbench.schemas.attempt_record import AttemptRecord
from agentbench.suite_runner import run_suite
from agentbench.tasks.exceptions import SuiteNotFoundError
from agentbench.tasks.loader import load_suite, load_task

logger = logging.getLogger(__name__)

app = typer.Typer(no_args_is_help=True)
console = Console()

setup_logging()

app.add_typer(report_app, name="report")


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
    if record.result.stop_reason:
        table.add_row("Stop Reason", str(record.result.stop_reason))
    
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
    log_llm_messages: bool | None = typer.Option(
        None,
        "--log-llm-messages/--no-log-llm-messages",
        help="Write LLM request/response pairs to llm_messages.jsonl.",
    ),
    strict_patch: bool = typer.Option(
        False,
        "--strict-patch/--no-strict-patch",
        help="Require strict unified diff patches (no auto-normalization).",
    ),
    skip_baseline: bool = typer.Option(
        False,
        "--skip-baseline",
        help="Skip baseline validation before running the agent.",
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
        
        # Auto-clean workspace from previous runs to avoid git clone conflicts
        if workspace_dir.exists():
            logger.debug("Cleaning up existing workspace at %s", workspace_dir)
            shutil.rmtree(workspace_dir, ignore_errors=True)
        
        workspace_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        console.print(f"[bold blue]Running agent '{variant}' on task '{task.id}'...[/bold blue]")

        if strict_patch:
            os.environ["AGENTBENCH_STRICT_PATCH"] = "1"
        else:
            os.environ.pop("AGENTBENCH_STRICT_PATCH", None)
        
        llm_config = None
        llm_client = None

        if variant == "llm_v0":
            api_key_str = os.getenv("OPENROUTER_API_KEY")
            if not api_key_str:
                console.print("[red]Error: OPENROUTER_API_KEY environment variable is required for llm_v0[/red]")
                raise typer.Exit(code=1)
            
            model_name = os.getenv("MODEL_NAME", "anthropic/claude-3.5-sonnet")
            
            llm_config = LLMConfig(
                provider_config=ProviderConfig(
                    provider=LLMProvider.OPENROUTER,
                    model_name=model_name,
                    api_key=SecretStr(api_key_str),
                    timeout_sec=120
                )
            )
            llm_client = OpenRouterClient(config=llm_config)

        record = run_agent_attempt(
            task=task,
            workspace_dir=workspace_dir,
            artifacts_dir=artifacts_dir,
            llm_config=llm_config,
            llm_client=llm_client,
            variant_override=variant,
            log_llm_messages=log_llm_messages,
            skip_baseline=skip_baseline,
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


@app.command("run-agent-suite")
def run_agent_suite_cmd(
    suite: str = typer.Argument(..., help="Suite name (matches tasks/<suite>/...)"),
    tasks_root: Path = typer.Option(Path("tasks"), "--tasks-root", "-r", help="Root directory containing task suites"),
    variant: str = typer.Option("scripted", "--variant", "-v", help="Agent variant (scripted or llm_v0)"),
    out_dir: Path = typer.Option(Path("artifacts"), "--out", "-o", help="Output directory for artifacts"),
    log_llm_messages: bool | None = typer.Option(
        None,
        "--log-llm-messages/--no-log-llm-messages",
        help="Write LLM request/response pairs to llm_messages.jsonl.",
    ),
    skip_baseline: bool = typer.Option(
        False,
        "--skip-baseline",
        help="Skip baseline validation before running the agent.",
    ),
):
    """
    Run an agent on every task in a suite sequentially.

    Artifacts are written under <out>/suite_runs/<suite>/<task_id>/.
    """
    try:
        tasks = load_suite(tasks_root=tasks_root, suite_name=suite)
    except SuiteNotFoundError:
        console.print(f"[red]Suite not found under {tasks_root}: {suite}[/red]")
        raise typer.Exit(code=1)

    if not tasks:
        console.print(f"[yellow]No tasks found in suite '{suite}'[/yellow]")
        raise typer.Exit(code=1)

    llm_config = None
    llm_client = None
    if variant == "llm_v0":
        api_key_str = os.getenv("OPENROUTER_API_KEY")
        if not api_key_str:
            console.print("[red]Error: OPENROUTER_API_KEY environment variable is required for llm_v0[/red]")
            raise typer.Exit(code=1)
        model_name = os.getenv("MODEL_NAME", "anthropic/claude-3.5-sonnet")
        llm_config = LLMConfig(
            provider_config=ProviderConfig(
                provider=LLMProvider.OPENROUTER,
                model_name=model_name,
                api_key=SecretStr(api_key_str),
                timeout_sec=120,
            )
        )
        llm_client = OpenRouterClient(config=llm_config)

    results: list[AttemptRecord] = []
    for task in tasks:
        console.print(f"[bold blue]Running agent '{variant}' on task '{task.id}'...[/bold blue]")
        workspace_dir = out_dir / "suite_runs" / suite / task.id / "workspace"
        artifacts_dir = out_dir / "suite_runs" / suite / task.id / "agent_runs"
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        record = run_agent_attempt(
            task=task,
            workspace_dir=workspace_dir,
            artifacts_dir=artifacts_dir,
            llm_config=llm_config,
            llm_client=llm_client,
            variant_override=variant,
            log_llm_messages=log_llm_messages,
            skip_baseline=skip_baseline,
        )
        results.append(record)
        print_agent_summary(record)
        console.print(f"[dim]Artifacts saved to: {artifacts_dir}[/dim]\n")

    # Suite summary
    summary = Table(title=f"Suite Run Summary: {suite}")
    summary.add_column("Task", style="cyan")
    summary.add_column("Success", style="green")
    summary.add_column("Exit", style="magenta")
    summary.add_column("Stop Reason", style="yellow")
    summary.add_column("Failure Reason", style="red")
    for rec in results:
        summary.add_row(
            rec.task_id,
            "✓" if rec.result.passed else "✗",
            str(rec.result.exit_code),
            str(rec.result.stop_reason or ""),
            str(rec.result.failure_reason or ""),
        )
    console.print(summary)


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


if __name__ == "__main__":  # pragma: no cover
    app()
