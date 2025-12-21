"""
Attempt Lifecycle Module

This module provides the AttemptContext context manager for crash-safe
attempt record writing. It guarantees that an AttemptRecord is written
to disk even if:
- A validation step throws an unhandled exception
- The sandbox runner crashes (Docker failure)
- The agent loop terminates unexpectedly
- The process receives SIGINT/SIGTERM

Usage:
    with AttemptContext(task, logs_dir, variant="baseline") as attempt:
        attempt.mark_stage("git_clone")
        # ... clone logic ...
        attempt.mark_stage("setup")
        # ... setup logic ...
        attempt.set_exit_code(exit_code)
        attempt.set_failure_reason(failure_reason)
    # AttemptContext.__exit__ automatically writes record
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import ulid

from agentbench.schemas.attempt_record import (
    AttemptRecord,
    BaselineValidationResult,
    LimitsConfig,
    TaskResult,
    TimestampInfo,
)
from agentbench.scoring.taxonomy import FailureReason
from agentbench.tasks.models import TaskSpec
from agentbench.util.jsonl import append_jsonl


class AttemptContext:
    """
    - Define `AttemptContext` class (context manager pattern):
    ```
        AttemptContext:
        __init__(task: TaskSpec, logs_dir: Path, variant: str)
        __enter__() -> AttemptContext
        __exit__(exc_type, exc_val, exc_tb) -> bool

        # Methods to call during execution:
        mark_stage(stage: str) -> None
        set_exit_code(code: int) -> None
        set_failure_reason(reason: FailureReason) -> None
        add_artifact(name: str, path: str) -> None

        # Internal:
        _write_record() -> None  # Called automatically in __exit__
        ```
    - Responsibilities:
        - Captures `started_at` on `__enter__`
        - Captures `ended_at` on `__exit__`
        - Always writes AttemptRecord to JSONL on `__exit__`
        - If exception occurred, maps it to `FailureReason.UNKNOWN` (or more specific if detectable)
        - Records which stage was in progress when failure occurred
    """

    def __init__(self, task: TaskSpec, logs_dir: Path, variant: str):
        self.task = task
        self.logs_dir = logs_dir
        self.variant = variant

        self.run_id = str(ulid.new())
        self.attempted = False
        self.valid = False

        self.current_stage = None
        self.exit_code = None
        self.failure_reason = None
        self.artifacts = {}
        self.started_at = None
        self.ended_at = None
        self.duration = None

    def mark_stage(self, stage: str) -> None:
        self.current_stage = stage

    def set_exit_code(self, code: int) -> None:
        self.exit_code = code

    def set_failure_reason(self, reason: FailureReason):
        self.failure_reason = reason

    def add_artifact(self, name: str, path: str):
        self.artifacts[name] = path

    def __enter__(self) -> AttemptContext:
        self.started_at = datetime.now()
        self.attempted = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.ended_at = datetime.now()

        if exc_type is not None:
            if exc_type is KeyboardInterrupt:
                self.failure_reason = FailureReason.INTERRUPTED
            elif self.failure_reason is None:
                self.failure_reason = FailureReason.UNKNOWN

        assert self.started_at is not None
        assert self.ended_at is not None

        self.duration = (self.ended_at - self.started_at).total_seconds()

        attempt_record = AttemptRecord(
            run_id=self.run_id,
            task_id=self.task.id,
            suite=self.task.suite,
            timestamps=TimestampInfo(
                started_at=self.started_at, ended_at=self.ended_at
            ),
            duration_sec=self.duration,
            baseline_validation=BaselineValidationResult(
                attempted=self.attempted,
                failure_as_expected=self.valid,
                exit_code=self.exit_code if self.exit_code is not None else -1,
            ),
            result=TaskResult(
                passed=self.valid,
                exit_code=self.exit_code if self.exit_code is not None else -1,
                failure_reason=self.failure_reason,
            ),
            artifact_paths=self.artifacts,
            variant=self.variant,
            model=None,
            limits=LimitsConfig(
                timeout_sec=self.task.environment.timeout_sec,
                tool_timeout_sec=None,
            ),
            schema_version="0.1.0",
        )
        attempts_file = self.logs_dir.parent / "attempts.jsonl"

        append_jsonl(attempts_file, attempt_record.model_dump(mode="json"))
        return False
