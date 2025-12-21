# AttemptRecord Schema Documentation

This document describes the schema for attempt records written to `attempts.jsonl`.

## Schema Version

The current schema version is **`0.1.0`** (pre-stable).

### Versioning Strategy

- **MAJOR**: Breaking changes (fields removed, types changed incompatibly)
- **MINOR**: New fields added (backwards compatible)  
- **PATCH**: Documentation/clarification only

Readers should check `schema_version` and handle unknown versions gracefully.

---

## Serialization Format

- **Format**: JSON Lines (`.jsonl`) - one JSON object per line
- **Timestamps**: ISO 8601 format with timezone (e.g., `"2025-12-17T10:00:00-05:00"`)
- **Nulls**: Represented as JSON `null`
- **Enums**: Serialized as uppercase strings (e.g., `"SETUP_FAILED"`)

---

## AttemptRecord Fields

| Field | Type | Required | When Populated | Example |
|-------|------|----------|----------------|---------|
| `schema_version` | str | Yes | Always | `"0.1.0"` |
| `run_id` | str | Yes | Always | `"01JFD..."` |
| `task_id` | str | Yes | Always | `"toy_fail_pytest"` |
| `suite` | str | Yes | Always | `"custom-dev"` |
| `variant` | str | Yes | Always | `"baseline"` |
| `model` | ModelConfig \| null | No | When agent runs | `null` for baseline |
| `timestamps.started_at` | datetime | Yes | Always | `"2025-12-17T10:00:00-05:00"` |
| `timestamps.ended_at` | datetime | Yes | Always | `"2025-12-17T10:02:30-05:00"` |
| `duration_sec` | float | Yes | Always | `150.5` |
| `baseline_validation.attempted` | bool | Yes | Always | `true` |
| `baseline_validation.failure_as_expected` | bool | Yes | Always | `true` |
| `baseline_validation.exit_code` | int | Yes | Always | `1` |
| `result.passed` | bool | Yes | Always | `false` |
| `result.exit_code` | int | Yes | Always | `1` |
| `result.failure_reason` | str \| null | No | When failed | `"SETUP_FAILED"` |
| `limits.timeout_sec` | int | Yes | Always | `300` |
| `limits.tool_timeout_sec` | int \| null | No | When tools enabled | `null` |
| `artifact_paths` | dict[str, str] | Yes | Always | `{"logs_dir": "..."}` |

---

## Nested Models

### TimestampInfo

Captures when the attempt started and ended.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `started_at` | datetime | Yes | When the attempt began (ISO 8601) |
| `ended_at` | datetime | Yes | When the attempt completed (ISO 8601) |

### BaselineValidationResult

Captures the outcome of baseline validation (running tests before any fix).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `attempted` | bool | Yes | Whether baseline validation was attempted |
| `failure_as_expected` | bool | Yes | Whether tests failed as expected (valid baseline) |
| `exit_code` | int | Yes | The pytest exit code from baseline run |

### TaskResult

Captures the final outcome of the task attempt.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `passed` | bool | Yes | Whether the task was completed successfully |
| `exit_code` | int | Yes | The final pytest exit code |
| `failure_reason` | FailureReason \| null | No | Enum code if failed, null if passed |

### ModelConfig

Captures LLM configuration when an agent runs. `null` for baseline validation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provider` | str \| null | No | LLM provider (e.g., "openrouter", "anthropic") |
| `name` | str \| null | No | Model name (e.g., "anthropic/claude-3.5-sonnet") |
| `temperature` | float \| null | No | Sampling temperature |
| `top_p` | float \| null | No | Nucleus sampling parameter |
| `max_tokens` | int \| null | No | Max completion tokens |
| `prompt_version` | str \| null | No | Hash of system prompt (e.g., "system_v1@sha256:abc...") |

### LimitsConfig

Captures timeout configuration for the attempt.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timeout_sec` | int | Yes | Overall task timeout in seconds |
| `tool_timeout_sec` | int \| null | No | Per-tool-call timeout (future use) |

---

## Backwards Compatibility

- Artifacts from Week 1-2 may not have `attempts.jsonl`
- Artifacts with `schema_version < "0.1.0"` are legacy
- Readers should check `schema_version` and handle gracefully
- Unknown fields should be ignored (forward compatibility)

---

## Example Record

```json
{
  "schema_version": "0.1.0",
  "run_id": "01JFDABCDEF123456789",
  "task_id": "toy_fail_pytest",
  "suite": "custom-dev",
  "variant": "baseline",
  "model": null,
  "timestamps": {
    "started_at": "2025-12-17T10:00:00-05:00",
    "ended_at": "2025-12-17T10:02:30-05:00"
  },
  "duration_sec": 150.5,
  "baseline_validation": {
    "attempted": true,
    "failure_as_expected": true,
    "exit_code": 1
  },
  "result": {
    "passed": true,
    "exit_code": 1,
    "failure_reason": null
  },
  "limits": {
    "timeout_sec": 300,
    "tool_timeout_sec": null
  },
  "artifact_paths": {
    "stdout": "logs/toy_fail_pytest/run_stdout.txt",
    "stderr": "logs/toy_fail_pytest/run_stderr.txt",
    "logs_dir": "logs/toy_fail_pytest"
  }
}
```
