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

# Default models to benchmark (edit this list as needed)
DEFAULT_MODELS = [
    # Free tier (likely won't work well)
    # "mistralai/devstral-2512:free",
    
    # Budget options
    "anthropic/claude-3-haiku",
    "openai/gpt-4o-mini",
    
    # Mid-tier
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
    
    # Top tier
    # "anthropic/claude-3-opus",
    # "openai/o1-preview",
]

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

def run_agent(task_path: str, model: str, out_dir: Path, timeout_sec: int) -> dict:
    """Run agent with a specific model and return results."""
    
    env = os.environ.copy()
    env["MODEL_NAME"] = model
    
    cmd = [
        sys.executable, "-c",
        "from agentbench.cli import app; app()",
        "run-agent",
        "--task", task_path,
        "--variant", "llm_v0",
        "--out", str(out_dir),
    ]
    
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
    
    # Parse results from output
    success = "Success" in stdout and "✓" in stdout
    
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

    return result_data


def print_results_table(results: list[dict]):
    """Print a nice summary table."""
    
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)
    print(f"{'Model':<45} {'Success':<10} {'Duration':<12} {'Exit':<6}")
    print("-" * 80)
    
    for r in results:
        if r.get("skipped"):
            success_str = "– SKIP"
        else:
            success_str = "✓ PASS" if r["success"] else "✗ FAIL"
        print(f"{r['model']:<45} {success_str:<10} {r['duration_sec']:>8.1f}s    {r['exit_code']:<6}")
    
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
    results = []
    
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
            result = run_agent(args.task, model, model_out, args.timeout_sec)
        if probe_results:
            result["probe"] = probe_results
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
