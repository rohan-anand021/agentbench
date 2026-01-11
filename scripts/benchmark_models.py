#!/usr/bin/env python3
"""
Benchmark multiple LLM models on a task.

Usage:
    python scripts/benchmark_models.py --task tasks/custom-dev/toy_fail_pytest/task.yaml

Or with a custom models file:
    python scripts/benchmark_models.py --task tasks/custom-dev/toy_fail_pytest/task.yaml --models models.txt
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from agentbench.tasks.loader import load_task
from agentbench.tasks.validator import validate_baseline
from agentbench.util.paths import ensure_dir

DEFAULT_MODELS_FILE = Path(__file__).with_name("models.txt")


def _load_default_models() -> list[str]:
    if DEFAULT_MODELS_FILE.is_file():
        models: list[str] = []
        with DEFAULT_MODELS_FILE.open() as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "#" in line:
                    line = line.split("#", 1)[0].strip()
                if line:
                    models.append(line)
        # Narrow to user-requested models if present
        filtered = [
            m for m in models
            if "kimi-k2" in m or "claude-3.7-sonnet" in m
        ]
        if filtered:
            return filtered
        return models
    # Fallback to explicit known IDs
    return [
        "moonshotai/kimi-k2",
        "anthropic/claude-3.7-sonnet",
    ]

# Default models to benchmark (edit this list as needed)
DEFAULT_MODELS = _load_default_models()


def _run_baseline_check(task_path: Path, out_dir: Path, sandbox_mode: str):
    """Run a baseline validation in the requested sandbox mode and ensure repo is not persisted locally."""
    task = load_task(task_path)
    baseline_root = ensure_dir(out_dir)
    workspace_dir = baseline_root / "workspace"
    logs_dir = baseline_root / "logs"
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir, ignore_errors=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nRunning baseline validation with sandbox_mode={sandbox_mode} in {baseline_root}...")
    baseline_result = validate_baseline(
        task=task,
        workspace_dir=workspace_dir,
        logs_dir=logs_dir,
        sandbox_mode=sandbox_mode,
    )
    repo_path = workspace_dir / "repo"
    if sandbox_mode == "ephemeral":
        if repo_path.exists():
            raise RuntimeError("Repo exists on host after ephemeral baseline; expected no host checkout")
        print("Verified: repo not present on host after ephemeral baseline.")
    if baseline_result.exit_code == 0:
        raise RuntimeError("Baseline validation passed unexpectedly - task is invalid")
    return baseline_result


def _maybe_override_docker_image(task_path: Path, override: str | None, out_dir: Path) -> Path:
    """If override is set, write a patched task file under out_dir and return its path."""
    if not override:
        return task_path
    with task_path.open() as f:
        data = yaml.safe_load(f)
    data.setdefault("environment", {})
    data["environment"]["docker_image"] = override
    patched_dir = ensure_dir(out_dir / "task_override")
    patched_path = patched_dir / task_path.name
    with patched_path.open("w") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    print(f"Using docker_image override: {override} (patched task at {patched_path})")
    return patched_path

def _find_events_path(out_dir: Path) -> Path | None:
    runs_dir = out_dir / "agent_runs"
    if not runs_dir.is_dir():
        return None
    candidates = sorted(runs_dir.glob("*/events.jsonl"))
    return candidates[-1] if candidates else None


def _read_last_llm_error(out_dir: Path) -> dict[str, Any] | None:
    events_path = _find_events_path(out_dir)
    if not events_path or not events_path.is_file():
        return None

    last_error = None
    try:
        with events_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event_type") == "llm_request_failed":
                    last_error = event.get("payload")
    except OSError:
        return None

    return last_error


def _read_last_agent_summary(out_dir: Path) -> dict[str, Any] | None:
    events_path = _find_events_path(out_dir)
    if not events_path or not events_path.is_file():
        return None

    last_summary = None
    try:
        with events_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event_type") == "agent_finished":
                    last_summary = event.get("payload")
    except OSError:
        return None

    return last_summary


def _read_last_tool_error(out_dir: Path) -> dict[str, Any] | None:
    events_path = _find_events_path(out_dir)
    if not events_path or not events_path.is_file():
        return None

    last_error = None
    try:
        with events_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event_type") == "tool_call_finished":
                    payload = event.get("payload") or {}
                    if payload.get("status") == "error":
                        last_error = payload
    except OSError:
        return None

    return last_error


def _probe_model(model: str, with_tools: bool) -> dict[str, Any]:
    import asyncio
    from pydantic import SecretStr
    from agentbench.llm.config import LLMConfig, ProviderConfig, LLMProvider, SamplingParams
    from agentbench.llm.messages import InputMessage, MessageRole, ToolDefinition
    from agentbench.llm.openrouter import OpenRouterClient
    from agentbench.llm.errors import LLMError

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {"success": False, "error": "OPENROUTER_API_KEY is not set"}

    tools = None
    if with_tools:
        tools = [
            ToolDefinition(
                name="probe_tool",
                description="Probe tool for model compatibility checks.",
                parameters={
                    "type": "object",
                    "properties": {"echo": {"type": "string"}},
                },
            )
        ]

    llm_config = LLMConfig(
        provider_config=ProviderConfig(
            provider=LLMProvider.OPENROUTER,
            model_name=model,
            api_key=SecretStr(api_key),
            timeout_sec=60,
        ),
        sampling=SamplingParams(temperature=0.0, max_tokens=128),
    )
    client = OpenRouterClient(config=llm_config)

    async def _call() -> dict[str, Any]:
        response = await client.complete(
            [InputMessage(role=MessageRole.USER, content="hello")],
            tools=tools,
        )
        return {
            "success": True,
            "has_tool_calls": response.has_tool_calls,
            "text_preview": (response.text_content or "")[:120],
        }

    try:
        return asyncio.run(_call())
    except LLMError as e:
        return {"success": False, "error": str(e)}


def _classify_probe_skip(probe_results: dict[str, Any]) -> str | None:
    def _msg(result: dict[str, Any] | None) -> str:
        if not result:
            return ""
        return str(result.get("error") or "")

    with_tools = probe_results.get("with_tools")
    no_tools = probe_results.get("no_tools")

    with_tools_msg = _msg(with_tools)
    no_tools_msg = _msg(no_tools)

    if "not a valid model ID" in with_tools_msg or "not a valid model ID" in no_tools_msg:
        return "invalid_model_id"
    if "No endpoints found that support tool use" in with_tools_msg:
        return "tools_not_supported"
    if with_tools_msg and no_tools_msg and "Internal Server Error" in with_tools_msg and "Internal Server Error" in no_tools_msg:
        return "provider_error"
    if with_tools and not with_tools.get("success") and (not no_tools or no_tools.get("success")):
        return "tools_probe_failed"

    return None

def run_agent(
    task_path: str,
    model: str,
    out_dir: Path,
    timeout_sec: int,
    log_llm_messages: bool | None = None,
    skip_baseline: bool = False,
    strict_patch: bool = False,
    sandbox_mode: str = "bind",
) -> dict:
    """Run agent with a specific model and return results."""
    
    env = os.environ.copy()
    env["MODEL_NAME"] = model
    if sandbox_mode != "bind":
        # Agent flow still requires host workspace; fallback to bind.
        print(f"  [warning] sandbox_mode={sandbox_mode} not supported for agent runs; using bind")
        sandbox_mode = "bind"
    
    cmd = [
        sys.executable, "-c",
        "from agentbench.cli import app; app()",
        "run-agent",
        "--task", task_path,
        "--variant", "llm_v0",
        "--out", str(out_dir),
        "--sandbox-mode", sandbox_mode,
    ]
    if log_llm_messages is True:
        cmd.append("--log-llm-messages")
    elif log_llm_messages is False:
        cmd.append("--no-log-llm-messages")
    if skip_baseline:
        cmd.append("--skip-baseline")
    if strict_patch:
        cmd.append("--strict-patch")
    
    start_time = datetime.now()
    
    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired:
        exit_code = -1
        stdout = ""
        stderr = "TIMEOUT: Model took too long"
    except Exception as e:
        exit_code = -2
        stdout = ""
        stderr = str(e)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    # Parse results from exit code (run-agent returns non-zero on failure)
    success = exit_code == 0
    
    result_data = {
        "model": model,
        "success": success,
        "exit_code": exit_code,
        "duration_sec": round(duration, 1),
        "stdout": stdout[-2000:] if stdout else "",  # Last 2000 chars
        "stderr": stderr[-1000:] if stderr else "",  # Last 1000 chars
    }

    llm_error = _read_last_llm_error(out_dir)
    if llm_error:
        result_data["llm_error_type"] = llm_error.get("error_type")
        result_data["llm_error_message"] = llm_error.get("message")
        result_data["llm_error_retryable"] = llm_error.get("retryable")

    agent_summary = _read_last_agent_summary(out_dir)
    if agent_summary:
        result_data["stop_reason"] = agent_summary.get("stop_reason")
        result_data["failure_reason"] = agent_summary.get("failure_reason")

    tool_error = _read_last_tool_error(out_dir)
    if tool_error:
        err = tool_error.get("error") or {}
        result_data["tool_error_type"] = err.get("error_type")
        result_data["tool_error_message"] = err.get("message")
        result_data["tool_name"] = tool_error.get("tool")

    return result_data


def _classify_failure(result: dict) -> str:
    """
    Rough categorization to disambiguate infra vs model vs task failures.
    """
    if result.get("skipped"):
        return "skipped"
    if result.get("success"):
        return "success"
    exit_code = result.get("exit_code", 0)
    failure_reason = (result.get("failure_reason") or "").upper()
    stop_reason = (result.get("stop_reason") or "").upper()
    if exit_code < 0:
        return "infra_runner"
    if result.get("llm_error_type"):
        return "infra_llm"
    if result.get("tool_error_type"):
        return "infra_agent"
    if failure_reason in {
        "SANDBOX_ERROR",
        "GIT_CLONE_FAILED",
        "GIT_CHECKOUT_FAILED",
        "SETUP_TIMEOUT",
    }:
        return "infra_task"
    if stop_reason in {"LLM_ERROR", "TOOL_ERROR"}:
        return "infra_agent"
    return "model_or_task"


def print_results_table(results: list[dict]):
    """Print a nice summary table."""
    
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)
    print(f"{'Model':<45} {'Success':<10} {'Duration':<12} {'Exit':<6} {'Reason'}")
    print("-" * 80)
    
    for r in results:
        if r.get("skipped"):
            success_str = "– SKIP"
        else:
            success_str = "✓ PASS" if r["success"] else "✗ FAIL"
        category = r.get("failure_category") or ""
        summary = r.get("failure_summary")
        reason = category
        if r.get("skipped"):
            reason = summary or r.get("skip_reason") or category
        elif not r.get("success"):
            reason = summary or r.get("failure_reason") or r.get("stop_reason") or ""
            if category and reason and category not in reason:
                reason = f"{category}: {reason}"
        print(
            f"{r['model']:<45} {success_str:<10} "
            f"{r['duration_sec']:>8.1f}s    {r['exit_code']:<6} {reason}"
        )
    
    print("-" * 80)
    
    # Summary
    passed = sum(1 for r in results if r["success"])
    skipped = sum(1 for r in results if r.get("skipped"))
    total = len(results)
    runnable = total - skipped
    print(f"\nTotal: {passed}/{runnable} models passed")
    if skipped:
        print(f"Skipped: {skipped}")
    
    if passed > 0:
        print("\nSuccessful models:")
        for r in results:
            if r["success"]:
                print(f"  - {r['model']} ({r['duration_sec']}s)")


def main():
    parser = argparse.ArgumentParser(description="Benchmark LLM models on a task")
    parser.add_argument("--task", required=True, help="Path to task.yaml")
    parser.add_argument("--models", help="Path to file with model names (one per line)")
    parser.add_argument("--out", default="artifacts/benchmark", help="Output directory")
    parser.add_argument(
        "--sandbox-mode",
        choices=["bind", "ephemeral"],
        default="ephemeral",
        help="Sandbox mode for baseline precheck (agent runs remain bind).",
    )
    parser.add_argument(
        "--docker-image-override",
        help="Override task.environment.docker_image (writes a patched task file for this run).",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=300,
        help="Timeout in seconds for each model run",
    )
    parser.add_argument(
        "--probe-mode",
        choices=["none", "no-tools", "with-tools", "both"],
        default="none",
        help="Optional probe calls before each run.",
    )
    parser.add_argument(
        "--strict-patch",
        action="store_true",
        help="Require strict unified diff patches (no auto-normalization).",
    )
    parser.add_argument(
        "--baseline-once",
        action="store_true",
        help="Run baseline validation once, then skip per-model baseline.",
    )
    parser.add_argument(
        "--skip-baseline",
        action="store_true",
        help="Skip baseline validation for each model run.",
    )
    log_group = parser.add_mutually_exclusive_group()
    log_group.add_argument(
        "--log-llm-messages",
        action="store_true",
        help=(
            "Write LLM request/response pairs to llm_messages.jsonl "
            "(overrides AGENTBENCH_LOG_LLM_MESSAGES)."
        ),
    )
    log_group.add_argument(
        "--no-log-llm-messages",
        action="store_true",
        help=(
            "Disable LLM request/response logging for this run "
            "(overrides AGENTBENCH_LOG_LLM_MESSAGES)."
        ),
    )
    args = parser.parse_args()
    
    # Load models
    if args.models:
        with open(args.models) as f:
            models = []
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Strip inline comments (e.g., "model/name  # comment")
                if "#" in line:
                    line = line.split("#")[0].strip()
                if line:
                    models.append(line)
    else:
        models = DEFAULT_MODELS
    
    print(f"Benchmarking {len(models)} models on {args.task}")
    print(f"Models:")
    for m in models:
        print(f"  - {m}")
    print()
    
    # Check for API key
    if not os.getenv("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY environment variable is required")
        sys.exit(1)
    
    out_dir = Path(args.out)
    task_path = Path(args.task)
    task_path_for_run = _maybe_override_docker_image(
        task_path=task_path,
        override=args.docker_image_override,
        out_dir=out_dir,
    )
    results = []

    # If using ephemeral mode, run a precheck to ensure repo stays in-container.
    if args.sandbox_mode == "ephemeral" and not args.baseline_once:
        try:
            _run_baseline_check(
                task_path=task_path_for_run,
                out_dir=Path(args.out) / "precheck_ephemeral",
                sandbox_mode=args.sandbox_mode,
            )
        except RuntimeError as err:
            print(f"ERROR during sandbox precheck: {err}")
            sys.exit(1)

    if args.baseline_once:
        try:
            _run_baseline_check(
                task_path=task_path_for_run,
                out_dir=Path(args.out) / "baseline",
                sandbox_mode=args.sandbox_mode,
            )
        except RuntimeError as err:
            print(f"ERROR during baseline validation: {err}")
            sys.exit(1)
    
    for i, model in enumerate(models, 1):
        print(f"\n[{i}/{len(models)}] Testing: {model}")
        print("-" * 40)

        probe_results = {}
        if args.probe_mode in {"no-tools", "both"}:
            probe_results["no_tools"] = _probe_model(model, with_tools=False)
        if args.probe_mode in {"with-tools", "both"}:
            probe_results["with_tools"] = _probe_model(model, with_tools=True)
        if probe_results:
            for label, probe in probe_results.items():
                if probe.get("success"):
                    preview = probe.get("text_preview") or ""
                    print(f"  Probe ({label}): ok {preview!r}")
                else:
                    print(f"  Probe ({label}): failed - {probe.get('error')}")

        skip_reason = _classify_probe_skip(probe_results) if probe_results else None
        if skip_reason == "invalid_model_id":
            print("  Skipping run: invalid model ID")
        elif skip_reason == "tools_not_supported":
            print("  Skipping run: model has no tool-enabled endpoints")
        elif skip_reason == "provider_error":
            print("  Skipping run: provider error during probe")
        elif skip_reason == "tools_probe_failed":
            print("  Skipping run: tool-enabled probe failed")

        # Each model gets its own output directory
        model_out = out_dir / model.replace("/", "_").replace(":", "_")

        log_llm_messages = None
        if args.log_llm_messages:
            log_llm_messages = True
        elif args.no_log_llm_messages:
            log_llm_messages = False

        skip_baseline = args.skip_baseline or args.baseline_once
        if skip_reason:
            result = {
                "model": model,
                "success": False,
                "exit_code": 0,
                "duration_sec": 0.0,
                "stdout": "",
                "stderr": "",
                "skipped": True,
                "skip_reason": skip_reason,
            }
        else:
            result = run_agent(
                str(task_path_for_run),
                model,
                model_out,
                args.timeout_sec,
                log_llm_messages=log_llm_messages,
                skip_baseline=skip_baseline,
                strict_patch=args.strict_patch,
                sandbox_mode=args.sandbox_mode,
            )
        if probe_results:
            result["probe"] = probe_results
        result["failure_category"] = _classify_failure(result)
        if result.get("tool_error_type"):
            summary = result.get("tool_error_type") or ""
            msg = result.get("tool_error_message")
            tool = result.get("tool_name")
            if tool:
                summary = f"{tool}: {summary}"
            if msg:
                summary = f"{summary} - {msg}"
            result["failure_summary"] = summary
        elif result.get("llm_error_type"):
            summary = result.get("llm_error_type") or ""
            msg = result.get("llm_error_message")
            if msg:
                summary = f"{summary} - {msg}"
            result["failure_summary"] = summary
        results.append(result)
        
        if result.get("skipped"):
            print("  – SKIPPED")
        elif result["success"]:
            print(f"  ✓ PASSED in {result['duration_sec']}s")
        else:
            print(f"  ✗ FAILED (exit={result['exit_code']}) in {result['duration_sec']}s")
            if result.get("llm_error_message"):
                print(
                    f"    LLM {result.get('llm_error_type')}: "
                    f"{result.get('llm_error_message')[:160]}"
                )
            reason_parts = []
            if result.get("failure_reason"):
                reason_parts.append(f"failure={result['failure_reason']}")
            if result.get("stop_reason"):
                reason_parts.append(f"stop={result['stop_reason']}")
            if reason_parts:
                print(f"    {', '.join(reason_parts)}")
            if result["stderr"]:
                # Show last few meaningful error lines (skip empty lines)
                lines = [l.strip() for l in result["stderr"].split("\n") if l.strip()]
                # Look for actual error messages (containing Error, Exception, Failed, etc.)
                error_lines = [l for l in lines if any(x in l for x in ["Error", "Exception", "Failed", "failed", "error:"])]
                if error_lines:
                    print(f"    {error_lines[-1][:100]}")
                elif lines:
                    print(f"    {lines[-1][:100]}")
    
    # Print summary
    print_results_table(results)
    
    # Save results
    results_file = out_dir / "benchmark_results.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, "w") as f:
        json.dump({
            "task": args.task,
            "timestamp": datetime.now().isoformat(),
            "results": results,
        }, f, indent=2)
    print(f"\nResults saved to: {results_file}")
    
    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
