#!/usr/bin/env sh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

FAST="${FAST:-0}"

run() {
  echo "+ $*"
  sh -c "$*"
}

# Detect Docker availability for docker-marked tests.
HAS_DOCKER=0
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    HAS_DOCKER=1
  fi
fi
export HAS_DOCKER

if [ "$FAST" = "1" ]; then
  run "pytest agentbench/tests --maxfail=1"
  exit 0
fi

run "pytest agentbench/tests --maxfail=1"

if [ "$HAS_DOCKER" -eq 1 ]; then
  run "pytest agentbench/tests -m docker --maxfail=1"
else
  echo "Skipping docker-marked tests; docker unavailable" >&2
fi

run "pytest agentbench/tests --maxfail=1 --cov=agentbench --cov-branch --cov-report=term-missing --cov-report=xml"
