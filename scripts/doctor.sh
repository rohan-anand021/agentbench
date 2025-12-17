#!/usr/bin/env bash
set -u

RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RESET="\033[0m"

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

check "Docker CLI available" docker version
check "Docker can run containers" docker run --rm hello-world
check "py-runner image exists" docker image inspect ghcr.io/agentbench/py-runner:0.1.0
check "Git available" git --version
check "Python available" python3 --version

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