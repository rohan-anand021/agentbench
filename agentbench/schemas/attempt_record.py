"""
AttemptRecord Schema Module

This module defines the Pydantic models for attempt records, which capture
the complete state of a task attempt including timing, validation results,
and failure reasons.

Schema Migration Notes:
- v0.1.0: Initial schema (Week 3)
- Future: When adding fields, increment MINOR version
- Future: When breaking changes, increment MAJOR version
- Readers should check schema_version and handle unknown versions gracefully

Versioning Strategy:
- schema_version uses semantic versioning: "MAJOR.MINOR.PATCH"
- MAJOR: Breaking changes (fields removed, types changed)
- MINOR: New fields added (backwards compatible)
- PATCH: Documentation/clarification only
"""

from datetime import datetime

from agentbench.scoring import FailureReason
from pydantic import BaseModel, ConfigDict, field_serializer


class TimestampInfo(BaseModel):
    model_config = ConfigDict(
        ser_json_timedelta="float",
    )

    started_at: datetime
    ended_at: datetime

    @field_serializer("started_at", "ended_at")
    def _serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()


class BaselineValidationResult(BaseModel):
    attempted: bool
    failed_as_expected: bool
    exit_code: int


class TaskResult(BaseModel):
    passed: bool
    exit_code: int
    failure_reason: FailureReason | None


class ModelConfig(BaseModel):
    """
    ### Create ModelConfig Schema
       - [ ] Add `ModelConfig` to `agentbench/schemas/attempt_record.py`:
       - `provider: str | None` — e.g., "openrouter", "anthropic", None for scripted
       - `name: str | None` — e.g., "anthropic/claude-3.5-sonnet", None for scripted
       - `temperature: float | None` — sampling temperature
       - `top_p: float | None` — nucleus sampling parameter
       - `max_tokens: int | None` — max completion tokens
       - `prompt_version: str | None` — hash of system prompt (e.g., "system_v1@sha256:abc123")
    """

    provider: str | None
    name: str | None
    temperature: float | None
    top_p: float | None
    max_tokens: int | None
    prompt_version: str | None


class LimitsConfig(BaseModel):
    """
    ### Create LimitsConfig Schema
        - [ ] Add `LimitsConfig` to `agentbench/schemas/attempt_record.py`:
        - `timeout_sec: int` — overall task timeout
        - `tool_timeout_sec: int | None` — per-tool-call timeout (optional, Week 4+)
    """

    timeout_sec: int
    tool_timeout_sec: int | None


class AttemptRecord(BaseModel):
    """
    - Define `AttemptRecord` Pydantic model matching spec:
        ```python
        class AttemptRecord(BaseModel):
            run_id: str
            task_id: str
            suite: str
            timestamps: TimestampInfo  # started_at, ended_at
            duration_sec: float
            baseline_validation: BaselineValidationResult
            result: TaskResult  # passed, exit_code, failure_reason
            artifact_paths: dict[str, str]
        ```
    - Nested models:
        - `TimestampInfo`: `started_at: datetime`, `ended_at: datetime`
        - `BaselineValidationResult`: `attempted: bool`, `failed_as_expected: bool`, `exit_code: int`
        - `TaskResult`: `passed: bool`, `exit_code: int`, `failure_reason: str | None`
    """

    model_config = ConfigDict(
        ser_json_timedelta="float",
    )

    run_id: str
    task_id: str
    suite: str
    task_spec_version: str
    harness_min_version: str | None
    labels: list[str] | None
    timestamps: TimestampInfo
    duration_sec: float
    baseline_validation: BaselineValidationResult
    result: TaskResult
    artifact_paths: dict[str, str]
    variant: str
    model: ModelConfig | None
    limits: LimitsConfig
    schema_version: str
