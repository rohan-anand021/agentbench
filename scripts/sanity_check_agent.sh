#!/usr/bin/env bash
# Sanity check for AgentBench Week 6

set -euo pipefail

echo "=== AgentBench Week 6 Sanity Check ==="

echo ""
echo "1) Imports"
PYTHONPATH=. venv/bin/python -c "from agentbench.agents.llm_v0 import LLMAgentV0; print('  Agent imports: OK')"
PYTHONPATH=. venv/bin/python -c "from agentbench.llm.openrouter import OpenRouterClient; print('  LLM client imports: OK')"

echo ""
echo "2) Validate custom-dev suite (baseline should fail)"
PYTHONPATH=. venv/bin/python -m agentbench.cli validate-suite custom-dev

echo ""
echo "3) Run agent on toy_one_liner (scripted)"
PYTHONPATH=. venv/bin/python -m agentbench.cli run-agent \
  --task tasks/custom-dev/toy_one_liner/task.yaml \
  --variant scripted \
  --out artifacts/sanity \
  --skip-baseline

echo ""
echo "4) Run suite command on custom-dev (scripted)"
PYTHONPATH=. venv/bin/python -m agentbench.cli run-agent-suite \
  custom-dev \
  --variant scripted \
  --tasks-root tasks \
  --out artifacts/sanity_suite \
  --skip-baseline

echo ""
echo "Done."
