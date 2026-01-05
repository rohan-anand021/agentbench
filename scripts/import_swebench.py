#!/usr/bin/env python3
"""Import selected SWE-bench tasks into AgentBench task format.

This script pulls SWE-bench Lite from Hugging Face, filters for fast tasks,
and writes AgentBench-compatible task.yaml files.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def load_swebench_lite(split: str = "test") -> list[dict[str, Any]]:
    """Load SWE-bench Lite instances.

    Requires the optional dependency `datasets`.
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover - import guard
        raise SystemExit(
            "The `datasets` package is required to load SWE-bench. "
            "Install with `pip install datasets`."
        ) from exc

    dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split=split)
    return list(dataset)


def filter_fast_tasks(
    instances: list[dict[str, Any]],
    max_test_time_sec: int = 60,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Filter SWE-bench instances for quick-running tasks.

    Heuristics:
    - Must have FAIL_TO_PASS tests listed.
    - If an estimated runtime is available and exceeds `max_test_time_sec`,
      skip the instance.
    - Stop after `limit` tasks.
    """
    selected: list[dict[str, Any]] = []
    for inst in instances:
        if limit and len(selected) >= limit:
            break
        fail_to_pass = inst.get("FAIL_TO_PASS") or []
        if not fail_to_pass:
            continue

        runtime = (
            inst.get("estimated_runtime")
            or inst.get("metadata", {}).get("estimated_runtime")
        )
        if runtime is not None and runtime > max_test_time_sec:
            continue

        selected.append(inst)

    return selected[:limit] if limit else selected


def _default_setup_commands() -> list[str]:
    return [
        "pip install --upgrade pip",
        # Build deps (avoid build isolation pulling newer setuptools)
        "pip install 'setuptools<69' wheel",
        "pip install 'setuptools_scm>=6.2'",
        "pip install 'oldest-supported-numpy' 'numpy<2'",
        "pip install 'cython==0.29.22'",
        "pip install extension-helpers",
        # Test runner
        "pip install pytest",
        # Build isolation can pull a newer setuptools; disable it to honor the pin.
        "pip install --no-build-isolation -e .",
    ]


def _normalize_fail_to_pass(raw: Any) -> list[str]:
    """Normalize FAIL_TO_PASS field into a list of test selectors."""
    if raw is None:
        return []
    value = raw
    # If the dataset stores this as a JSON string, parse it.
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
            value = parsed
        except Exception:
            value = [value]
    if isinstance(value, (list, tuple)):
        items = []
        for item in value:
            if item is None:
                continue
            items.append(str(item).strip())
        return [i for i in items if i]
    return [str(value).strip()]


def _build_run_command(fail_to_pass: Any) -> str:
    tests = _normalize_fail_to_pass(fail_to_pass)
    if tests:
        joined = " ".join(tests)
        return f"pytest -q {joined}"
    return "pytest -q"


def generate_task_yaml(
    instance: dict[str, Any],
    output_dir: Path,
    suite: str = "swe-bench-lite",
    docker_image: str = "ghcr.io/agentbench/py-runner:0.1.0",
    timeout_sec: int = 180,
) -> Path:
    """Generate a task.yaml for a SWE-bench instance."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fail_to_pass = instance.get("FAIL_TO_PASS")
    repo = instance["repo"]
    repo_url = f"https://github.com/{repo}"

    task = {
        "task_spec_version": "1.0",
        "id": instance["instance_id"],
        "suite": suite,
        "repo": {
            "url": repo_url,
            "commit": instance["base_commit"],
        },
        "environment": {
            "docker_image": docker_image,
            "workdir": "/workspace",
            "timeout_sec": int(timeout_sec),
        },
        "setup": {
            "commands": _default_setup_commands(),
        },
        "run": {
            "command": _build_run_command(fail_to_pass),
        },
        "agent": {
            "entrypoint": "llm_v0",
            "max_steps": 20,
        },
        "labels": ["swe-bench-lite"],
    }

    task_path = output_dir / "task.yaml"
    with task_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(task, f, sort_keys=False)
    return task_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import SWE-bench Lite tasks into AgentBench format."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tasks") / "swe-bench-lite-10",
        help="Directory to write tasks into (one subdir per instance).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of tasks to import.",
    )
    parser.add_argument(
        "--max-test-time-sec",
        type=int,
        default=60,
        help="Skip tasks whose estimated runtime exceeds this (when available).",
    )
    parser.add_argument(
        "--docker-image",
        type=str,
        default="ghcr.io/agentbench/py-runner:0.1.0",
        help="Docker image to use in generated task specs.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=180,
        help="Timeout for generated task run commands.",
    )
    parser.add_argument(
        "--suite",
        type=str,
        default="swe-bench-lite",
        help="Suite name to embed in generated tasks.",
    )

    args = parser.parse_args()

    instances = load_swebench_lite()
    selected = filter_fast_tasks(
        instances,
        max_test_time_sec=args.max_test_time_sec,
        limit=args.limit,
    )

    output_root = args.output_dir
    output_root.mkdir(parents=True, exist_ok=True)

    for inst in selected:
        task_dir = output_root / inst["instance_id"]
        generate_task_yaml(
            inst,
            task_dir,
            suite=args.suite,
            docker_image=args.docker_image,
            timeout_sec=args.timeout_sec,
        )

    print(f"Wrote {len(selected)} tasks to {output_root}")


if __name__ == "__main__":
    main()
