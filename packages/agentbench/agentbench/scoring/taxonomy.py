"""
Failure Taxonomy Module

This module defines the FailureReason enum, which provides a deterministic
taxonomy of all possible failure states in the evaluation harness.

Key design decisions:
- Success is represented by None, not by an enum value
- Uses Python's StrEnum for automatic string serialization
- All mapping logic is co-located as @classmethod methods on the enum
- Timeout exit codes (124, 137) are checked BEFORE stage-specific logic

See scoring/README.md for complete documentation of failure codes,
precedence rules, and exit code mappings.
"""

from enum import StrEnum


class FailureReason(StrEnum):
    """
    Enum of all possible failure reasons in the evaluation harness.

    Success is represented by `None`, not by an enum value.
    This enum only contains failure states.

    | Code | Description | When to Use |
    |------|-------------|-------------|
    | `SETUP_FAILED` | Dependency install failure, missing tools | Setup command returns non-zero (not timeout) |
    | `SETUP_TIMEOUT` | Setup exceeded time limit | Setup command returns exit code 124 or 137 |
    | `BASELINE_NOT_FAILING` | Task is invalid (tests pass before fix) | Baseline validation: exit code 0 |
    | `TIMEOUT` | Run command exceeded time limit | Run command returns exit code 124 or 137 |
    | `SANDBOX_ERROR` | Docker issues, container failures | Docker command fails, container won't start |
    | `GIT_CLONE_FAILED` | Could not clone repository | git clone returns non-zero |
    | `GIT_CHECKOUT_FAILED` | Could not checkout commit | git checkout returns non-zero |
    | `TOOL_ERROR` | Patch apply failure, invalid file ops | Tool returns structured error (Week 4+) |
    | `TESTS_FAILED` | Tests still fail after agent attempts | Post-agent pytest exit != 0 |
    | `AGENT_GAVE_UP` | Hit max steps without success | Agent exhausted step budget (Week 6+) |
    | `LLM_ERROR` | Rate limit, API failure, invalid response | LLM call fails (Week 5+) |
    | `NO_TESTS_COLLECTED` | pytest found no tests | pytest exit code 5 |
    | `INTERNAL_ERROR` | pytest internal error | pytest exit code 3 or 4 |
    | `INTERRUPTED` | User cancelled (Ctrl+C) | SIGINT received |
    | `UNKNOWN` | Catch-all for unexpected failures | Any unmapped error |
    """

    SETUP_FAILED = "SETUP_FAILED"
    SETUP_TIMEOUT = "SETUP_TIMEOUT"
    BASELINE_NOT_FAILING = "BASELINE_NOT_FAILING"
    TIMEOUT = "TIMEOUT"
    SANDBOX_ERROR = "SANDBOX_ERROR"
    GIT_CLONE_FAILED = "GIT_CLONE_FAILED"
    GIT_CHECKOUT_FAILED = "GIT_CHECKOUT_FAILED"
    TOOL_ERROR = "TOOL_ERROR"
    TESTS_FAILED = "TESTS_FAILED"
    AGENT_GAVE_UP = "AGENT_GAVE_UP"
    LLM_ERROR = "LLM_ERROR"
    NO_TESTS_COLLECTED = "NO_TESTS_COLLECTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INTERRUPTED = "INTERRUPTED"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_pytest_exit_code(cls, exit_code: int) -> "FailureReason | None":
        """
        Map a pytest exit code to a FailureReason.

        Args:
            exit_code: The pytest process exit code.

        Returns:
            FailureReason if tests failed, None if tests passed (exit code 0).

        Exit code mapping:
            - 0 → None (success, no failure)
            - 1 → TESTS_FAILED
            - 2 → INTERRUPTED (user interruption)
            - 3 → INTERNAL_ERROR (pytest internal error)
            - 4 → INTERNAL_ERROR (command line usage error)
            - 5 → NO_TESTS_COLLECTED
            - 124 → TIMEOUT (GNU timeout convention)
            - 137 → TIMEOUT (SIGKILL, likely OOM or timeout)
            - other → UNKNOWN
        """
        match exit_code:
            case 0:
                return None
            case 1:
                return cls.TESTS_FAILED
            case 2:
                return cls.INTERRUPTED
            case 3 | 4:
                return cls.INTERNAL_ERROR
            case 5:
                return cls.NO_TESTS_COLLECTED
            case 124 | 137:
                return cls.TIMEOUT
            case _:
                return cls.UNKNOWN

    @classmethod
    def from_stage(
        cls,
        stage: str,
        exit_code: int,
        exception: Exception | None = None,
    ) -> "FailureReason | None":
        """
        Determine failure reason based on execution stage and exit code.

        Args:
            stage: One of "git_clone", "git_checkout", "setup",
                   "baseline_run", "agent_run", "final_test".
            exit_code: The command's exit code.
            exception: Python exception if one was raised, or None.

        Returns:
            FailureReason if the stage failed, None if it succeeded.

        Logic:
            1. Handle exceptions first (KeyboardInterrupt → INTERRUPTED, other → UNKNOWN)
            2. Check for timeout exit codes (124, 137) BEFORE stage-specific logic
            3. Apply stage-specific logic for non-timeout exit codes
        """

        if exception is not None:
            if isinstance(exception, KeyboardInterrupt):
                return cls.INTERRUPTED
            return cls.UNKNOWN

        if exit_code in (124, 137):
            if stage == "setup":
                return cls.SETUP_TIMEOUT
            return cls.TIMEOUT

        match stage:
            case "git_clone":
                return cls.GIT_CLONE_FAILED if exit_code != 0 else None
            case "git_checkout":
                return cls.GIT_CHECKOUT_FAILED if exit_code != 0 else None
            case "setup":
                return cls.SETUP_FAILED if exit_code != 0 else None
            case "baseline_run":
                if exit_code == 0:
                    return cls.BASELINE_NOT_FAILING
                return None
            case "agent_run" | "final_test":
                return cls.from_pytest_exit_code(exit_code)
            case _:
                raise ValueError(f"Unknown stage: {stage!r}")

    @property
    def precedence(self) -> int:
        """
        Return the precedence of this failure reason (lower = higher priority).

        When multiple failures occur, the one with lower precedence value
        should be reported as the primary failure reason.

        Precedence order (earlier stage failures dominate):
            1. GIT_CLONE_FAILED (can't even get the code)
            2. GIT_CHECKOUT_FAILED (can't get correct version)
            3. SETUP_TIMEOUT (setup never completed)
            4. SETUP_FAILED (dependencies broken)
            5. BASELINE_NOT_FAILING (task is invalid)
            6. SANDBOX_ERROR (execution environment broken)
            7. LLM_ERROR (can't get agent responses)
            8. TOOL_ERROR (agent's tool calls fail)
            9. TIMEOUT (ran out of time)
            10. AGENT_GAVE_UP (budget exhausted)
            11. TESTS_FAILED (agent tried but didn't fix)
            12. NO_TESTS_COLLECTED, INTERNAL_ERROR, INTERRUPTED, UNKNOWN
        """
        precedence_order = {
            FailureReason.GIT_CLONE_FAILED: 1,
            FailureReason.GIT_CHECKOUT_FAILED: 2,
            FailureReason.SETUP_TIMEOUT: 3,
            FailureReason.SETUP_FAILED: 4,
            FailureReason.BASELINE_NOT_FAILING: 5,
            FailureReason.SANDBOX_ERROR: 6,
            FailureReason.LLM_ERROR: 7,
            FailureReason.TOOL_ERROR: 8,
            FailureReason.TIMEOUT: 9,
            FailureReason.AGENT_GAVE_UP: 10,
            FailureReason.TESTS_FAILED: 11,
            FailureReason.NO_TESTS_COLLECTED: 12,
            FailureReason.INTERNAL_ERROR: 13,
            FailureReason.INTERRUPTED: 14,
            FailureReason.UNKNOWN: 15,
        }
        return precedence_order.get(self, 99)
