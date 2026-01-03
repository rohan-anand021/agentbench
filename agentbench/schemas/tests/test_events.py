"""Unit tests for Event schema."""

import json
from datetime import datetime, timezone

import pytest
from agentbench.schemas.events import Event, EventType
from pydantic import ValidationError


class TestEventTypeEnum:
    """Tests for EventType enum values."""

    def test_all_event_types_exist(self):
        """All expected event types are defined."""
        expected_types = [
            "TOOL_CALL_STARTED",
            "TOOL_CALL_FINISHED",
            "AGENT_TURN_STARTED",
            "AGENT_TURN_FINISHED",
            "PATCH_APPLIED",
            "TESTS_STARTED",
            "TESTS_FINISHED",
            "TASK_STARTED",
            "TASK_FINISHED",
        ]
        for event_type in expected_types:
            assert hasattr(EventType, event_type)

    def test_event_type_values_are_snake_case(self):
        """Event type values are snake_case strings."""
        assert EventType.TOOL_CALL_STARTED.value == "tool_call_started"
        assert EventType.TOOL_CALL_FINISHED.value == "tool_call_finished"
        assert EventType.PATCH_APPLIED.value == "patch_applied"

    def test_event_type_is_str_enum(self):
        """EventType values can be used as strings."""
        assert str(EventType.TOOL_CALL_STARTED) == "tool_call_started"
        assert f"{EventType.PATCH_APPLIED}" == "patch_applied"


class TestEventCreation:
    """Tests for Event model creation."""

    def test_create_event_with_all_fields(self):
        """Event can be created with all required fields."""
        event = Event(
            event_type=EventType.TOOL_CALL_STARTED,
            timestamp=datetime.now(timezone.utc),
            run_id="run_001",
            step_id=1,
            payload={"tool_name": "read_file", "params": {"path": "foo.py"}},
        )

        assert event.event_type == EventType.TOOL_CALL_STARTED
        assert event.event_version == "1.0"
        assert event.run_id == "run_001"
        assert event.step_id == 1
        assert "tool_name" in event.payload

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


class TestEventSerialization:
    """Tests for Event serialization."""

    def test_event_round_trip_json(self):
        """Event can be serialized to JSON and deserialized back."""
        original = Event(
            event_type=EventType.PATCH_APPLIED,
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            run_id="run_abc123",
            step_id=5,
            payload={"files_modified": ["src/main.py"], "success": True},
        )

        json_data = json.loads(original.model_dump_json())
        restored = Event.model_validate(json_data)

        assert restored.event_type == original.event_type
        assert restored.event_version == original.event_version
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

        json_data = json.loads(event.model_dump_json())
        assert "2024-01-15" in json_data["timestamp"]

    def test_event_payload_with_nested_structures(self):
        """Event payload can contain nested structures."""
        event = Event(
            event_type=EventType.TOOL_CALL_FINISHED,
            timestamp=datetime.now(timezone.utc),
            run_id="run_001",
            step_id=3,
            payload={
                "tool_name": "search",
                "params": {"query": "def main", "options": {"max_results": 10}},
                "result": {"matches": [{"file": "a.py", "line": 5}]},
            },
        )

        json_data = json.loads(event.model_dump_json())
        restored = Event.model_validate(json_data)

        assert restored.payload["params"]["options"]["max_results"] == 10
        assert restored.payload["result"]["matches"][0]["file"] == "a.py"


class TestEventTypes:
    """Tests for specific event types."""

    def test_tool_call_events(self):
        """Tool call events can be created."""
        started = Event(
            event_type=EventType.TOOL_CALL_STARTED,
            timestamp=datetime.now(timezone.utc),
            run_id="run_001",
            step_id=1,
            payload={"tool_name": "read_file"},
        )
        finished = Event(
            event_type=EventType.TOOL_CALL_FINISHED,
            timestamp=datetime.now(timezone.utc),
            run_id="run_001",
            step_id=2,
            payload={"tool_name": "read_file", "status": "success"},
        )

        assert started.event_type == EventType.TOOL_CALL_STARTED
        assert finished.event_type == EventType.TOOL_CALL_FINISHED

    def test_agent_turn_events(self):
        """Agent turn events can be created."""
        started = Event(
            event_type=EventType.AGENT_TURN_STARTED,
            timestamp=datetime.now(timezone.utc),
            run_id="run_001",
            step_id=1,
            payload={"turn": 1},
        )
        finished = Event(
            event_type=EventType.AGENT_TURN_FINISHED,
            timestamp=datetime.now(timezone.utc),
            run_id="run_001",
            step_id=2,
            payload={"turn": 1, "actions": 3},
        )

        assert started.event_type == EventType.AGENT_TURN_STARTED
        assert finished.event_type == EventType.AGENT_TURN_FINISHED

    def test_task_lifecycle_events(self):
        """Task lifecycle events can be created."""
        started = Event(
            event_type=EventType.TASK_STARTED,
            timestamp=datetime.now(timezone.utc),
            run_id="run_001",
            step_id=0,
            payload={"task_id": "task_001"},
        )
        finished = Event(
            event_type=EventType.TASK_FINISHED,
            timestamp=datetime.now(timezone.utc),
            run_id="run_001",
            step_id=100,
            payload={"task_id": "task_001", "passed": True},
        )

        assert started.event_type == EventType.TASK_STARTED
        assert finished.event_type == EventType.TASK_FINISHED
