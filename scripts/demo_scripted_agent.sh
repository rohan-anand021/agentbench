#!/bin/bash
set -e

echo "=== Week 4 Demo: Scripted Agent ==="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

DEMO_OUT="artifacts/demo"
rm -rf "$DEMO_OUT"
mkdir -p "$DEMO_OUT"

echo "Running the scripted agent on toy_fail_pytest..."
echo ""

uv run agentbench run-agent \
    --task tasks/custom-dev/toy_fail_pytest/task.yaml \
    --variant scripted \
    --out "$DEMO_OUT"

echo ""
echo "=== Artifacts Created ==="
find "$DEMO_OUT" -type f | head -20

if [ -f "$DEMO_OUT/agent_runs/toy_fail_pytest/events.jsonl" ]; then
    echo ""
    echo "=== Events Log (last 10 entries) ==="
    tail -10 "$DEMO_OUT/agent_runs/toy_fail_pytest/events.jsonl" | jq -c '.event_type'
fi

if [ -f "$DEMO_OUT/agent_runs/toy_fail_pytest/diffs/step_0004.patch" ]; then
    echo ""
    echo "=== Patch Applied ==="
    cat "$DEMO_OUT/agent_runs/toy_fail_pytest/diffs/step_0004.patch"
fi

echo ""
echo "=== Demo Complete ==="
