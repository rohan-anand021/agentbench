import json
import signal
from collections import Counter
from datetime import datetime
from pathlib import Path

import ulid
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from agentbench.tasks.loader import load_suite
from agentbench.tasks.validator import validate_baseline
from agentbench.util.jsonl import append_jsonl
from agentbench.util.process import ensure_dir

console = Console()


class SuiteInterrupted(Exception):
    """Raised when suite run is interrupted by SIGINT."""

    pass


def run_suite(suite_name: str, tasks_root: Path, out_dir: Path) -> Path:
    """
    Run baseline validation on all tasks in a suite.

    Loads tasks, validates each one, and produces structured logs.
    - Load all tasks in suite using `load_suite()`
    - Create run directory: `<out_dir>/runs/<timestamp>__<suite>__baseline/`
    - Create `run.json` metadata file
    - For each task: run `validate_baseline()`, append to `attempts.jsonl`
    - Update `run.json` with:
        - `ended_at: datetime`
        - `valid_count: int`
        - `invalid_count: int`
        - Return run directory path
    """

    tasks = load_suite(tasks_root=tasks_root, suite_name=suite_name)

    # Handle empty suite
    if not tasks:
        console.print(
            f"[yellow]Warning:[/yellow] No tasks found in suite '{suite_name}'"
        )
        return None

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = ensure_dir(
        Path(out_dir / "runs" / f"{timestamp}__{suite_name}__baseline")
    )
    run_id = str(ulid.new())
    run_json_path = Path(run_dir / "run.json")
    started_at = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    logs_parent_dir = Path(run_dir / "logs")
    attempts_jsonl_path = Path(logs_parent_dir, "attempts.jsonl")

    runs_data = {
        "run_id": run_id,
        "suite": suite_name,
        "started_at": started_at,
        "task_count": len(tasks),
        "harness_version": "dev",
    }

    with run_json_path.open("w") as f:
        json.dump(runs_data, f, indent=2)

    valid_count = 0
    invalid_count = 0
    results = []
    interrupted = False

    # Set up SIGINT handler
    def handle_sigint(signum, frame):
        nonlocal interrupted
        interrupted = True
        console.print("\n[yellow]Interrupted! Saving progress...[/yellow]")

    original_handler = signal.signal(signal.SIGINT, handle_sigint)

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task_progress = progress.add_task(
                f"[cyan]Validating {suite_name}...", total=len(tasks)
            )

            for i, task in enumerate(tasks):
                if interrupted:
                    break

                # create task-specific workspace subdirectory
                task_workspace = ensure_dir(
                    Path(run_dir / "workspace" / task.id)
                )

                try:
                    # run validate baseline
                    validation_result = validate_baseline(
                        task=task,
                        workspace_dir=task_workspace,
                        logs_dir=Path(logs_parent_dir / task.id),
                    )

                    append_jsonl(
                        attempts_jsonl_path,
                        validation_result.model_dump(mode="json"),
                    )

                    if validation_result.valid:
                        valid_count += 1
                        status = "[green]VALID[/green]"
                    else:
                        invalid_count += 1
                        status = "[red]INVALID[/red]"

                    results.append(
                        (
                            task.id,
                            validation_result.valid,
                            validation_result.error_reason,
                        )
                    )
                    console.print(
                        f"  Task {i + 1}/{len(tasks)}: {task.id}... {status}"
                    )
                except Exception as e:
                    # Handle partial failures - continue with other tasks
                    invalid_count += 1
                    results.append((task.id, False, f"error: {str(e)}"))
                    err_msg = f"  Task {i + 1}/{len(tasks)}: {task.id}..."
                    console.print(f"{err_msg} [red]ERROR[/red] ({e})")

                progress.advance(task_progress)
    finally:
        # Restore original signal handler
        signal.signal(signal.SIGINT, original_handler)

    ended_at = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    final_run_data = {
        "ended_at": ended_at,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
    }

    if interrupted:
        final_run_data["interrupted"] = True

    runs_data.update(final_run_data)

    with run_json_path.open("w") as f:
        json.dump(runs_data, f, indent=2)

    # Summary table
    console.print()
    console.print("═" * 44)
    console.print(f"[bold]Suite Validation Complete: {suite_name}[/bold]")
    console.print("═" * 44)

    table = Table(title="Task Results")
    table.add_column("Task ID", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Reason", style="dim")

    for task_id, valid, error_reason in results:
        status = "[green]VALID[/green]" if valid else "[red]INVALID[/red]"
        reason = error_reason or "-"
        table.add_row(task_id, status, reason)

    console.print(table)
    console.print()

    # Summary counts
    total_processed = len(results)
    valid_pct = (valid_count / total_processed * 100) if total_processed else 0
    console.print(f"[bold]Total tasks:[/bold]    {len(tasks)}")
    console.print(
        f"[green]Valid:[/green]          {valid_count} ({valid_pct:.0f}%)"
    )
    console.print(
        f"[red]Invalid:[/red]        {invalid_count} ({100 - valid_pct:.0f}%)"
    )

    # Failure reason breakdown
    failure_reasons = [
        reason for _, valid, reason in results if not valid and reason
    ]
    if failure_reasons:
        reason_counts = Counter(failure_reasons)
        for reason, count in reason_counts.items():
            console.print(f"  [dim]- {reason}: {count}[/dim]")

    if interrupted:
        skipped = len(tasks) - total_processed
        console.print(
            f"\n[yellow]Run was interrupted. {skipped} tasks skipped.[/yellow]"
        )

    console.print(f"\n[dim]Run artifacts:[/dim] {run_dir}")

    return run_dir
