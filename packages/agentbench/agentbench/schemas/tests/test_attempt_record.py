from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from agentbench.schemas.attempt_record import (
    AttemptRecord,
    BaselineValidationResult,
    LimitsConfig,
    ModelConfig,
    TaskResult,
    TimestampInfo,
)


def make_valid_attempt_record(**overrides) -> AttemptRecord:
    """Helper to create a valid AttemptRecord with optional overrides."""
    defaults = {
        "run_id": "01ABC123XYZ",
        "task_id": "test-task-id",
        "suite": "test-suite",
        "timestamps": TimestampInfo(
            started_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
            ended_at=datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC),
        ),
        "duration_sec": 300.0,
        "baseline_validation": BaselineValidationResult(
            attempted=True,
            failure_as_expected=True,
            exit_code=1,
        ),
        "result": TaskResult(
            passed=True,
            exit_code=0,
            failure_reason=None,
        ),
        "artifact_paths": {"logs": "/path/to/logs"},
        "variant": "baseline",
        "model": None,
        "limits": LimitsConfig(timeout_sec=600, tool_timeout_sec=None),
        "schema_version": "1.0",
    }
    defaults.update(overrides)
    return AttemptRecord(**defaults)


class TestAttemptRecordCreation:
    """Test: Create AttemptRecord with all required fields → success"""

    def test_create_with_all_required_fields_succeeds(self):
        record = make_valid_attempt_record()

        assert record.run_id == "01ABC123XYZ"
        assert record.task_id == "test-task-id"
        assert record.suite == "test-suite"
        assert record.duration_sec == 300.0
        assert record.variant == "baseline"
        assert record.schema_version == "1.0"
        assert record.model is None
        assert record.limits.timeout_sec == 600


class TestAttemptRecordMissingFields:
    """Test: Missing required fields → ValidationError"""

    def test_missing_run_id_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            AttemptRecord(
                # run_id is missing
                task_id="test-task-id",
                suite="test-suite",
                timestamps=TimestampInfo(
                    started_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
                    ended_at=datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC),
                ),
                duration_sec=300.0,
                baseline_validation=BaselineValidationResult(
                    attempted=True, failure_as_expected=True, exit_code=1
                ),
                result=TaskResult(
                    passed=True, exit_code=0, failure_reason=None
                ),
                artifact_paths={},
                variant="baseline",
                model=None,
                limits=LimitsConfig(timeout_sec=600, tool_timeout_sec=None),
                schema_version="1.0",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("run_id",) for e in errors)

    def test_missing_schema_version_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            AttemptRecord(
                run_id="01ABC123XYZ",
                task_id="test-task-id",
                suite="test-suite",
                timestamps=TimestampInfo(
                    started_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
                    ended_at=datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC),
                ),
                duration_sec=300.0,
                baseline_validation=BaselineValidationResult(
                    attempted=True, failure_as_expected=True, exit_code=1
                ),
                result=TaskResult(
                    passed=True, exit_code=0, failure_reason=None
                ),
                artifact_paths={},
                variant="baseline",
                model=None,
                limits=LimitsConfig(timeout_sec=600, tool_timeout_sec=None),
                # schema_version is missing
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("schema_version",) for e in errors)


class TestAttemptRecordModelField:
    """Test: model=None is valid for baseline runs"""

    def test_model_none_is_valid_for_baseline_runs(self):
        record = make_valid_attempt_record(variant="baseline", model=None)

        assert record.model is None
        assert record.variant == "baseline"

    def test_model_with_config_is_valid(self):
        model_config = ModelConfig(
            provider="anthropic",
            name="claude-3.5-sonnet",
            temperature=0.7,
            top_p=0.9,
            max_tokens=4096,
            prompt_version="system_v1@sha256:abc123",
        )
        record = make_valid_attempt_record(model=model_config)

        assert record.model is not None
        assert record.model.provider == "anthropic"
        assert record.model.name == "claude-3.5-sonnet"


class TestAttemptRecordRoundTrip:
    """Test: Round-trip: model_dump(mode='json') → model_validate() produces equivalent object"""

    def test_round_trip_produces_equivalent_object(self):
        original = make_valid_attempt_record()

        # Serialize to JSON-compatible dict
        json_dict = original.model_dump(mode="json")

        # Deserialize back to AttemptRecord
        restored = AttemptRecord.model_validate(json_dict)

        # Compare all fields
        assert restored.run_id == original.run_id
        assert restored.task_id == original.task_id
        assert restored.suite == original.suite
        assert restored.duration_sec == original.duration_sec
        assert restored.variant == original.variant
        assert restored.schema_version == original.schema_version
        assert restored.model == original.model
        assert restored.limits == original.limits
        assert restored.result == original.result
        assert restored.baseline_validation == original.baseline_validation
        assert restored.artifact_paths == original.artifact_paths
        # Timestamps comparison (datetimes are restored correctly)
        assert restored.timestamps.started_at == original.timestamps.started_at
        assert restored.timestamps.ended_at == original.timestamps.ended_at

    def test_round_trip_with_model_config(self):
        model_config = ModelConfig(
            provider="openrouter",
            name="anthropic/claude-3.5-sonnet",
            temperature=0.5,
            top_p=None,
            max_tokens=8192,
            prompt_version=None,
        )
        original = make_valid_attempt_record(model=model_config)

        json_dict = original.model_dump(mode="json")
        restored = AttemptRecord.model_validate(json_dict)

        assert restored.model == original.model


class TestTimestampSerialization:
    """Test: Timestamps serialize to ISO 8601 strings"""

    def test_timestamps_serialize_to_iso8601_strings(self):
        record = make_valid_attempt_record()

        json_dict = record.model_dump(mode="json")

        # Check that timestamps are strings in ISO 8601 format
        started_at = json_dict["timestamps"]["started_at"]
        ended_at = json_dict["timestamps"]["ended_at"]

        assert isinstance(started_at, str)
        assert isinstance(ended_at, str)

        # Verify ISO 8601 format (should contain 'T' separator and timezone)
        assert "T" in started_at
        assert "T" in ended_at

        # Verify the values are correct ISO 8601 representations
        assert started_at == "2025-01-01T10:00:00Z"
        assert ended_at == "2025-01-01T10:05:00Z"

    def test_timestamps_with_different_timezone(self):
        from datetime import timedelta

        # Create timestamps with a non-UTC timezone
        tz_offset = timezone(timedelta(hours=-5))
        record = make_valid_attempt_record(
            timestamps=TimestampInfo(
                started_at=datetime(2025, 6, 15, 14, 30, 0, tzinfo=tz_offset),
                ended_at=datetime(2025, 6, 15, 15, 0, 0, tzinfo=tz_offset),
            )
        )

        json_dict = record.model_dump(mode="json")

        started_at = json_dict["timestamps"]["started_at"]
        ended_at = json_dict["timestamps"]["ended_at"]

        assert isinstance(started_at, str)
        assert isinstance(ended_at, str)
        # Should contain timezone offset
        assert "-05:00" in started_at
        assert "-05:00" in ended_at
