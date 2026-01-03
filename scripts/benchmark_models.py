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


def run_agent(task_path: str, model: str, out_dir: Path) -> dict:
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
            timeout=300,  # 5 minute timeout per model
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
    
    return {
        "model": model,
        "success": success,
        "exit_code": exit_code,
        "duration_sec": round(duration, 1),
        "stdout": stdout[-2000:] if stdout else "",  # Last 2000 chars
        "stderr": stderr[-1000:] if stderr else "",  # Last 1000 chars
    }


def print_results_table(results: list[dict]):
    """Print a nice summary table."""
    
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)
    print(f"{'Model':<45} {'Success':<10} {'Duration':<12} {'Exit':<6}")
    print("-" * 80)
    
    for r in results:
        success_str = "✓ PASS" if r["success"] else "✗ FAIL"
        print(f"{r['model']:<45} {success_str:<10} {r['duration_sec']:>8.1f}s    {r['exit_code']:<6}")
    
    print("-" * 80)
    
    # Summary
    passed = sum(1 for r in results if r["success"])
    total = len(results)
    print(f"\nTotal: {passed}/{total} models passed")
    
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
        
        # Each model gets its own output directory
        model_out = out_dir / model.replace("/", "_").replace(":", "_")
        
        result = run_agent(args.task, model, model_out)
        results.append(result)
        
        if result["success"]:
            print(f"  ✓ PASSED in {result['duration_sec']}s")
        else:
            print(f"  ✗ FAILED (exit={result['exit_code']}) in {result['duration_sec']}s")
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

