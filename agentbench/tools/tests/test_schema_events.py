"""Unit tests for tools/schemas/events module."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agentbench.tools.schemas.events import Event, EventType


class TestToolSchemaEventTypeEnum:
    """Tests for EventType enum in tools/schemas."""

    def test_event_type_tool_call_values(self):
        """Tool call event types have correct values."""
        assert EventType.TOOL_CALL_STARTED.value == "tool_call_started"
        assert EventType.TOOL_CALL_FINISHED.value == "tool_call_finished"

    def test_event_type_agent_turn_values(self):
        """Agent turn event types have correct values."""
        assert EventType.AGENT_TURN_STARTED.value == "agent_turn_started"
        assert EventType.AGENT_TURN_FINISHED.value == "agent_turn_finished"

    def test_event_type_task_lifecycle_values(self):
        """Task lifecycle event types have correct values."""
        assert EventType.TASK_STARTED.value == "task_started"
        assert EventType.TASK_FINISHED.value == "task_finished"

    def test_event_type_other_values(self):
        """Other event types have correct values."""
        assert EventType.PATCH_APPLIED.value == "patch_applied"
        assert EventType.TESTS_STARTED.value == "tests_started"
        assert EventType.TESTS_FINISHED.value == "tests_finished"

    def test_event_type_is_str_enum(self):
        """EventType values can be used as strings."""
        assert str(EventType.TOOL_CALL_STARTED) == "tool_call_started"
        assert f"{EventType.PATCH_APPLIED}" == "patch_applied"


class TestToolSchemaEventModel:
    """Tests for Event Pydantic model in tools/schemas."""

    def test_event_creation(self):
        """Event can be created with all required fields."""
        event = Event(
            event_type=EventType.TOOL_CALL_STARTED,
            timestamp=datetime.now(timezone.utc),
            run_id="run_001",
            step_id=1,
            payload={"tool_name": "read_file"},
        )

        assert event.event_type == EventType.TOOL_CALL_STARTED
        assert event.run_id == "run_001"
        assert event.step_id == 1

    def test_event_requires_event_type(self):
        """Event requires event_type field."""
        with pytest.raises(ValidationError):
            Event(
                timestamp=datetime.now(timezone.utc),
                run_id="run_001",
                step_id=1,
                payload={},
            )

    def test_event_requires_timestamp(self):
        """Event requires timestamp field."""
        with pytest.raises(ValidationError):
            Event(
                event_type=EventType.TOOL_CALL_STARTED,
                run_id="run_001",
                step_id=1,
                payload={},
            )

    def test_event_requires_run_id(self):
        """Event requires run_id field."""
        with pytest.raises(ValidationError):
            Event(
                event_type=EventType.TOOL_CALL_STARTED,
                timestamp=datetime.now(timezone.utc),
                step_id=1,
                payload={},
            )

    def test_event_requires_step_id(self):
        """Event requires step_id field."""
        with pytest.raises(ValidationError):
            Event(
                event_type=EventType.TOOL_CALL_STARTED,
                timestamp=datetime.now(timezone.utc),
                run_id="run_001",
                payload={},
            )

    def test_event_requires_payload(self):
        """Event requires payload field."""
        with pytest.raises(ValidationError):
            Event(
                event_type=EventType.TOOL_CALL_STARTED,
                timestamp=datetime.now(timezone.utc),
                run_id="run_001",
                step_id=1,
            )

    def test_event_payload_can_be_empty_dict(self):
        """Event payload can be an empty dictionary."""
        event = Event(
            event_type=EventType.TASK_STARTED,
            timestamp=datetime.now(timezone.utc),
            run_id="run_001",
            step_id=0,
            payload={},
        )
        assert event.payload == {}


class TestToolSchemaEventSerialization:
    """Tests for Event JSON serialization in tools/schemas."""

    def test_event_round_trip_json(self):
        """Event can be serialized to JSON and deserialized back."""
        original = Event(
            event_type=EventType.PATCH_APPLIED,
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            run_id="run_abc123",
            step_id=5,
            payload={"files_modified": ["src/main.py"], "success": True},
        )

        json_data = original.model_dump(mode="json")
        restored = Event.model_validate(json_data)

        assert restored.event_type == original.event_type
        assert restored.run_id == original.run_id
        assert restored.step_id == original.step_id
        assert restored.payload == original.payload

    def test_event_timestamp_serializes_to_iso_format(self):
        """Event timestamp serializes to ISO 8601 format."""
        event = Event(
            event_type=EventType.TASK_FINISHED,
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            run_id="run_001",
            step_id=10,
            payload={"exit_code": 0},
        )

        json_data = event.model_dump(mode="json")
        assert "2024-01-15" in json_data["timestamp"]
