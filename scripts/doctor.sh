#!/usr/bin/env bash
set -u

RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RESET="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SMOKE_TASK="${REPO_ROOT}/tasks/custom-dev/toy_pass_pytest/task.yaml"
SMOKE_OUT="${REPO_ROOT}/artifacts/doctor"

FAILED=0

echo "Running environment checks..."
echo

check() {
  local description="$1"
  shift

  if "$@" >/dev/null 2>&1; then
    echo -e "${GREEN}PASS${RESET} $description"
  else
    echo -e "${RED}FAIL${RESET} $description"
    FAILED=1
  fi
}

warn_check() {
  local description="$1"
  shift

  if "$@" >/dev/null 2>&1; then
    echo -e "${GREEN}PASS${RESET} $description"
  else
    echo -e "${YELLOW}WARN${RESET} $description"
  fi
}

run_smoke_task() {
  if [ ! -f "$SMOKE_TASK" ]; then
    return 1
  fi

  PYTHONPATH="$REPO_ROOT" REPO_ROOT="$REPO_ROOT" SMOKE_TASK="$SMOKE_TASK" \
    SMOKE_OUT="$SMOKE_OUT" python3 - <<'PY'
import os
from pathlib import Path

from agentbench.run_task import run_task

repo_root = Path(os.environ["REPO_ROOT"])
task_yaml = Path(os.environ["SMOKE_TASK"])
out_dir = Path(os.environ["SMOKE_OUT"])

os.chdir(repo_root)
run_task(task_yaml, out_dir)
PY
}

check_network_isolation() {
  docker run --rm --network none ghcr.io/agentbench/py-runner:0.1.0 python - <<'PY'
import sys
import urllib.request

try:
    urllib.request.urlopen("https://example.com", timeout=2)
    sys.exit(1)
except Exception:
    sys.exit(0)
PY
}

check "Docker CLI available" docker version
check "Docker can run containers" docker run --rm hello-world
warn_check "Pull runner image" docker pull ghcr.io/agentbench/py-runner:0.1.0
check "py-runner image exists" docker image inspect ghcr.io/agentbench/py-runner:0.1.0
check "Network isolation blocks outbound" check_network_isolation
check "Git available" git --version
check "Python available" python3 --version
check "End-to-end task run (toy_pass_pytest)" run_smoke_task

echo
echo "Checking disk space..."

AVAILABLE_KB=$(df -k . | tail -1 | awk '{print $4}')
AVAILABLE_GB=$((AVAILABLE_KB / 1024 / 1024))

if [ "$AVAILABLE_GB" -lt 10 ]; then
  echo -e "${YELLOW}WARN${RESET} Low disk space: ${AVAILABLE_GB}GB available"
else
  echo -e "${GREEN}PASS${RESET} Disk space: ${AVAILABLE_GB}GB available"
fi

echo
echo "======================"
echo "Doctor summary"
echo "======================"

if [ "$FAILED" -eq 0 ]; then
  echo -e "${GREEN}All checks passed${RESET}"
  exit 0
else
  echo -e "${RED}Some checks failed${RESET}"
  exit 1
fi
