# Failure Taxonomy Documentation

This document describes the `FailureReason` enum used to categorize why a task attempt failed.

## Overview

Success is represented by `None` (or `null` in JSON), not by an enum value.
The `FailureReason` enum only contains failure states.

---

## Failure Codes

| Code | Description | Typical Cause |
|------|-------------|---------------|
| `SETUP_FAILED` | Setup command failed | Missing dependency, broken pip install |
| `SETUP_TIMEOUT` | Setup exceeded timeout | Slow network, large dependencies |
| `BASELINE_NOT_FAILING` | Tests pass before fix | Invalid task (already fixed) |
| `TIMEOUT` | Run command exceeded timeout | Infinite loop, slow tests |
| `SANDBOX_ERROR` | Docker/container failure | Docker daemon down, OOM |
| `GIT_CLONE_FAILED` | Could not clone repo | Bad URL, network failure |
| `GIT_CHECKOUT_FAILED` | Could not checkout commit | Invalid commit SHA |
| `TOOL_ERROR` | Agent tool call failed | Invalid patch, path escape |
| `TESTS_FAILED` | Tests fail after agent | Agent didn't fix the bug |
| `AGENT_GAVE_UP` | Agent hit step limit | Complex bug, bad strategy |
| `LLM_ERROR` | LLM API failure | Rate limit, invalid key |
| `NO_TESTS_COLLECTED` | pytest found no tests | Wrong test path, missing tests |
| `INTERNAL_ERROR` | pytest internal error | Broken conftest, import error |
| `INTERRUPTED` | User cancelled | Ctrl+C |
| `UNKNOWN` | Unexpected error | Uncaught exception |

---

## Precedence Rules

When multiple failures could apply, the one with lower precedence number is reported as the primary failure reason. Earlier stage failures dominate.

| Precedence | Code | Rationale |
|------------|------|-----------|
| 1 | `GIT_CLONE_FAILED` | Can't even get the code |
| 2 | `GIT_CHECKOUT_FAILED` | Can't get correct version |
| 3 | `SETUP_TIMEOUT` | Setup never completed |
| 4 | `SETUP_FAILED` | Dependencies broken |
| 5 | `BASELINE_NOT_FAILING` | Task is invalid |
| 6 | `SANDBOX_ERROR` | Execution environment broken |
| 7 | `LLM_ERROR` | Can't get agent responses |
| 8 | `TOOL_ERROR` | Agent's tool calls fail |
| 9 | `TIMEOUT` | Ran out of time |
| 10 | `AGENT_GAVE_UP` | Budget exhausted |
| 11 | `TESTS_FAILED` | Agent tried but didn't fix |
| 12 | `NO_TESTS_COLLECTED` | Testing infrastructure issue |
| 13 | `INTERNAL_ERROR` | pytest internal failure |
| 14 | `INTERRUPTED` | User cancellation |
| 15 | `UNKNOWN` | Catch-all |

---

## Exit Code Mappings

### pytest Exit Codes → FailureReason

| Exit Code | FailureReason | Meaning |
|-----------|---------------|---------|
| 0 | `None` | Tests passed |
| 1 | `TESTS_FAILED` | Tests ran but failed |
| 2 | `INTERRUPTED` | User interrupted (Ctrl+C) |
| 3 | `INTERNAL_ERROR` | pytest internal error |
| 4 | `INTERNAL_ERROR` | Command line usage error |
| 5 | `NO_TESTS_COLLECTED` | No tests found |
| 124 | `TIMEOUT` | GNU timeout killed process |
| 137 | `TIMEOUT` | SIGKILL (OOM or timeout) |
| other | `UNKNOWN` | Unexpected exit code |

### Stage-Aware Mapping

The `from_stage()` method determines failure reason based on execution stage:

1. **Exceptions first**: `KeyboardInterrupt` → `INTERRUPTED`, other → `UNKNOWN`
2. **Timeout exit codes second** (124, 137): These override stage-specific logic
   - Setup stage → `SETUP_TIMEOUT`
   - Other stages → `TIMEOUT`
3. **Stage-specific logic last**:
   - `git_clone`: non-zero → `GIT_CLONE_FAILED`
   - `git_checkout`: non-zero → `GIT_CHECKOUT_FAILED`
   - `setup`: non-zero → `SETUP_FAILED`
   - `baseline_run`: exit 0 → `BASELINE_NOT_FAILING`, non-zero → `None` (valid)
   - `agent_run`/`final_test`: use pytest exit code mapping

---

## Failure Scenarios and Expected Codes

| Scenario | Exit Code | Stage | Expected FailureReason |
|----------|-----------|-------|------------------------|
| Valid baseline (tests fail) | 1 | baseline_run | `None` |
| Invalid task (tests pass) | 0 | baseline_run | `BASELINE_NOT_FAILING` |
| pip install fails | 1 | setup | `SETUP_FAILED` |
| Setup takes too long | 124 | setup | `SETUP_TIMEOUT` |
| Tests hang forever | 124 | agent_run | `TIMEOUT` |
| Bad git URL | 128 | git_clone | `GIT_CLONE_FAILED` |
| User presses Ctrl+C | 2 | any | `INTERRUPTED` |
| git clone hangs | 124 | git_clone | `TIMEOUT` |
| Docker fails to start | varies | any | `SANDBOX_ERROR` |

---

## Usage Examples

```python
from agentbench.scoring import FailureReason

# Map pytest exit code
reason = FailureReason.from_pytest_exit_code(1)
# Returns: FailureReason.TESTS_FAILED

# Map stage + exit code
reason = FailureReason.from_stage("setup", 1)
# Returns: FailureReason.SETUP_FAILED

# Timeout during setup
reason = FailureReason.from_stage("setup", 124)
# Returns: FailureReason.SETUP_TIMEOUT

# Valid baseline (tests fail as expected)
reason = FailureReason.from_stage("baseline_run", 1)
# Returns: None (success, not a failure)

# Get precedence for comparison
if reason1.precedence < reason2.precedence:
    primary_reason = reason1
```
