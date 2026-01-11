#!/usr/bin/env python3
"""
Iterate over tasks in a suite, find ones with failing baselines, and run a single model on them.

- Loads OPENROUTER_API_KEY from .env (if present) via python-dotenv.
- Uses ephemeral sandbox for baselines to avoid host workspace pollution.
- Runs the specified model (default: moonshotai/kimi-k2) via the existing run_agent helper from benchmark_models.
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path for imports
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

from agentbench.tasks.loader import load_task, discover_tasks
from agentbench.tasks.validator import validate_baseline
from agentbench.util.paths import ensure_dir
from scripts.benchmark_models import run_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Find failing-baseline tasks and benchmark a model.")
    parser.add_argument(
        "--suite-root",
        default="tasks/swe-bench-lite-10",
        help="Path to suite root containing task folders.",
    )
    parser.add_argument(
        "--out",
        default="artifacts/discover",
        help="Output directory for artifacts.",
    )
    parser.add_argument(
        "--model",
        default="moonshotai/kimi-k2",
        help="Model name to benchmark.",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=3,
        help="Max number of failing-baseline tasks to run.",
    )
    args = parser.parse_args()

    load_dotenv()  # load OPENROUTER_API_KEY if present
    if not os.getenv("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set (set in env or .env).", file=sys.stderr)
        sys.exit(1)

    suite_root = Path(args.suite_root)
    out_root = Path(args.out)
    tasks = discover_tasks(suite_root)

    print(f"Discovered {len(tasks)} tasks under {suite_root}")

    processed = 0
    for task_path in tasks:
        if processed >= args.max_tasks:
            break

        print(f"\n--- Baseline check: {task_path} ---")
        task = load_task(task_path)
        task_out = out_root / task.id
        baseline_workspace = ensure_dir(task_out / "baseline" / "workspace")
        baseline_logs = ensure_dir(task_out / "baseline" / "logs")

        # Clean any previous workspace
        if baseline_workspace.exists():
            for child in baseline_workspace.iterdir():
                if child.is_dir():
                    for sub in child.iterdir():
                        if sub.is_file():
                            sub.unlink()
                    child.rmdir()
                else:
                    child.unlink()

        validation = validate_baseline(
            task=task,
            workspace_dir=baseline_workspace,
            logs_dir=baseline_logs,
            sandbox_mode="ephemeral",
        )

        if validation.exit_code == 0:
            print(f"Baseline PASSED (unexpected) for {task.id}; skipping.")
            continue

        print(f"Baseline failed as expected (exit_code={validation.exit_code}); benchmarking model {args.model}...")

        model_out = task_out / "model_runs"
        model_out.mkdir(parents=True, exist_ok=True)

        result = run_agent(
            task_path=str(task_path),
            model=args.model,
            out_dir=model_out,
            timeout_sec=task.environment.timeout_sec,
            log_llm_messages=None,
            skip_baseline=True,  # already checked baseline above
            strict_patch=False,
            sandbox_mode="bind",  # agent flow remains bind-backed
        )
        print(f"Model run complete: success={result.get('success')} exit_code={result.get('exit_code')}")
        processed += 1

    if processed == 0:
        print("No failing-baseline tasks were processed. Adjust task selection or tests.")


if __name__ == "__main__":
    main()
