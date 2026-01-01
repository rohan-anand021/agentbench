"""
Day 3 Checkpoint Tests:
- append_jsonl() correctly writes records
- read_jsonl() correctly reads them back
- Schema validates correctly with Pydantic
"""

import json
from datetime import datetime

import pytest

from agentbench.schemas.attempt_record import (
    AttemptRecord,
    BaselineValidationResult,
    TaskResult,
    TimestampInfo,
)
from agentbench.util.jsonl import append_jsonl, read_jsonl


class TestAppendJsonl:
    """Tests for append_jsonl function."""

    def test_append_creates_file_if_not_exists(self, tmp_path):
        """append_jsonl should create the file if it doesn't exist."""
        jsonl_file = tmp_path / "test.jsonl"
        record = {"key": "value", "number": 42}

        append_jsonl(jsonl_file, record)

        assert jsonl_file.exists()

    def test_append_writes_valid_json(self, tmp_path):
        """append_jsonl should write valid JSON that can be parsed back."""
        jsonl_file = tmp_path / "test.jsonl"
        record = {"key": "value", "nested": {"a": 1, "b": 2}}

        append_jsonl(jsonl_file, record)

        content = jsonl_file.read_text()
        parsed = json.loads(content.strip())
        assert parsed == record

    def test_append_adds_newline(self, tmp_path):
        """Each record should end with a newline."""
        jsonl_file = tmp_path / "test.jsonl"
        record = {"key": "value"}

        append_jsonl(jsonl_file, record)

        content = jsonl_file.read_text()
        assert content.endswith("\n")

    def test_append_multiple_records(self, tmp_path):
        """Multiple appends should create multiple lines."""
        jsonl_file = tmp_path / "test.jsonl"
        records = [
            {"id": 1, "name": "first"},
            {"id": 2, "name": "second"},
            {"id": 3, "name": "third"},
        ]

        for record in records:
            append_jsonl(jsonl_file, record)

        lines = jsonl_file.read_text().strip().split("\n")
        assert len(lines) == 3

        for i, line in enumerate(lines):
            parsed = json.loads(line)
            assert parsed == records[i]

    def test_append_creates_parent_directories(self, tmp_path):
        """append_jsonl should create parent directories if they don't exist."""
        jsonl_file = tmp_path / "nested" / "deeply" / "test.jsonl"
        record = {"key": "value"}

        append_jsonl(jsonl_file, record)

        assert jsonl_file.exists()
        assert jsonl_file.parent.exists()


class TestReadJsonl:
    """Tests for read_jsonl function."""

    def test_read_single_record(self, tmp_path):
        """read_jsonl should correctly read a single record."""
        jsonl_file = tmp_path / "test.jsonl"
        record = {"key": "value", "number": 42}
        jsonl_file.write_text(json.dumps(record) + "\n")

        results = list(read_jsonl(jsonl_file))

        assert len(results) == 1
        assert results[0] == record

    def test_read_multiple_records(self, tmp_path):
        """read_jsonl should correctly read multiple records."""
        jsonl_file = tmp_path / "test.jsonl"
        records = [
            {"id": 1, "name": "first"},
            {"id": 2, "name": "second"},
            {"id": 3, "name": "third"},
        ]
        content = "\n".join(json.dumps(r) for r in records) + "\n"
        jsonl_file.write_text(content)

        results = list(read_jsonl(jsonl_file))

        assert len(results) == 3
        assert results == records

    def test_read_skips_empty_lines(self, tmp_path):
        """read_jsonl should skip empty lines."""
        jsonl_file = tmp_path / "test.jsonl"
        content = '{"id": 1}\n\n{"id": 2}\n   \n{"id": 3}\n'
        jsonl_file.write_text(content)

        results = list(read_jsonl(jsonl_file))

        assert len(results) == 3
        assert [r["id"] for r in results] == [1, 2, 3]

    def test_read_handles_malformed_lines(self, tmp_path):
        """read_jsonl should skip malformed lines without crashing."""
        jsonl_file = tmp_path / "test.jsonl"
        content = '{"id": 1}\nnot valid json\n{"id": 2}\n'
        jsonl_file.write_text(content)

        results = list(read_jsonl(jsonl_file))

        # Should skip the malformed line and return only valid records
        assert len(results) == 2
        assert [r["id"] for r in results] == [1, 2]

    def test_read_returns_iterator(self, tmp_path):
        """read_jsonl should return an iterator, not a list."""
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text('{"id": 1}\n')

        result = read_jsonl(jsonl_file)

        # Should be an iterator/generator, not a list
        assert hasattr(result, "__iter__")
        assert hasattr(result, "__next__")


class TestRoundTrip:
    """Tests for append and read working together."""

    def test_append_then_read(self, tmp_path):
        """Records written with append_jsonl should be readable with read_jsonl."""
        jsonl_file = tmp_path / "test.jsonl"
        records = [
            {"id": 1, "data": "first", "nested": {"a": 1}},
            {"id": 2, "data": "second", "nested": {"b": 2}},
        ]

        for record in records:
            append_jsonl(jsonl_file, record)

        results = list(read_jsonl(jsonl_file))

        assert results == records


class TestAttemptRecordSchema:
    """Tests for AttemptRecord Pydantic schema validation."""

    def _make_valid_attempt_record(self) -> dict:
        """Helper to create a valid attempt record dict."""
        return {
            "run_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "task_id": "toy_fail_pytest",
            "suite": "custom-dev",
            "timestamps": {
                "started_at": "2025-01-01T12:00:00",
                "ended_at": "2025-01-01T12:01:00",
            },
            "duration_sec": 60.0,
            "baseline_validation": {
                "attempted": True,
                "failure_as_expected": True,
                "exit_code": 1,
            },
            "result": {
                "passed": True,
                "exit_code": 1,
                "failure_reason": None,
            },
            "artifact_paths": {
                "stdout": "/path/to/stdout.txt",
                "stderr": "/path/to/stderr.txt",
            },
            "variant": "baseline",
            "model": None,
            "limits": {
                "timeout_sec": 300,
                "tool_timeout_sec": None,
            },
            "schema_version": "0.1.0",
        }

    def test_valid_attempt_record(self):
        """A valid AttemptRecord should be created without errors."""
        data = self._make_valid_attempt_record()
        record = AttemptRecord(**data)

        assert record.run_id == data["run_id"]
        assert record.task_id == data["task_id"]
        assert record.suite == data["suite"]
        assert record.duration_sec == 60.0
        assert record.baseline_validation.attempted is True
        assert record.result.passed is True

    def test_timestamp_info_parsing(self):
        """TimestampInfo should correctly parse datetime strings."""
        data = self._make_valid_attempt_record()
        record = AttemptRecord(**data)

        assert isinstance(record.timestamps.started_at, datetime)
        assert isinstance(record.timestamps.ended_at, datetime)

    def test_nested_models_validation(self):
        """Nested models should be properly validated."""
        data = self._make_valid_attempt_record()
        record = AttemptRecord(**data)

        assert isinstance(record.baseline_validation, BaselineValidationResult)
        assert isinstance(record.result, TaskResult)
        assert isinstance(record.timestamps, TimestampInfo)

    def test_missing_required_field_raises_error(self):
        """Missing required fields should raise ValidationError."""
        from pydantic import ValidationError

        data = self._make_valid_attempt_record()
        del data["run_id"]

        with pytest.raises(ValidationError):
            AttemptRecord(**data)

    def test_invalid_type_raises_error(self):
        """Invalid types should raise ValidationError."""
        from pydantic import ValidationError

        data = self._make_valid_attempt_record()
        data["duration_sec"] = "not a number"

        with pytest.raises(ValidationError):
            AttemptRecord(**data)

    def test_model_dump_json_roundtrip(self, tmp_path):
        """AttemptRecord should serialize to JSON and deserialize correctly."""
        data = self._make_valid_attempt_record()
        record = AttemptRecord(**data)

        # Serialize to JSON-compatible dict
        json_data = record.model_dump(mode="json")

        # Write to JSONL and read back
        jsonl_file = tmp_path / "attempts.jsonl"
        append_jsonl(jsonl_file, json_data)

        results = list(read_jsonl(jsonl_file))
        assert len(results) == 1

        # Parse back to AttemptRecord
        restored = AttemptRecord(**results[0])

        assert restored.run_id == record.run_id
        assert restored.task_id == record.task_id
        assert restored.duration_sec == record.duration_sec
        assert (
            restored.baseline_validation.attempted
            == record.baseline_validation.attempted
        )
        assert restored.result.passed == record.result.passed

    def test_failure_reason_can_be_none(self):
        """TaskResult.failure_reason should accept None."""
        data = self._make_valid_attempt_record()
        data["result"]["failure_reason"] = None

        record = AttemptRecord(**data)
        assert record.result.failure_reason is None

    def test_failure_reason_can_be_string(self):
        """TaskResult.failure_reason should accept a FailureReason enum string."""
        data = self._make_valid_attempt_record()
        data["result"]["failure_reason"] = "SETUP_FAILED"

        record = AttemptRecord(**data)
        assert record.result.failure_reason == "SETUP_FAILED"
