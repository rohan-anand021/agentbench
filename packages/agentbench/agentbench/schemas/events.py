from enum import StrEnum
from datetime import datetime
from pydantic import BaseModel
from typing import Any


class EventType(StrEnum):
    # Tool events
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_FINISHED = "tool_call_finished"

    # Agent events (for Day 4)
    AGENT_TURN_STARTED = "agent_turn_started"
    AGENT_TURN_FINISHED = "agent_turn_finished"

    # Patch events
    PATCH_APPLIED = "patch_applied"

    # Test events
    TESTS_STARTED = "tests_started"
    TESTS_FINISHED = "tests_finished"

    # Task lifecycle
    TASK_STARTED = "task_started"
    TASK_FINISHED = "task_finished"


class Event(BaseModel):
    """Base event for all logged actions."""

    event_type: EventType
    timestamp: datetime
    run_id: str  # Links to AttemptRecord
    step_id: int  # Sequential step number in this run
    payload: dict[str, Any]  # Event-specific data
