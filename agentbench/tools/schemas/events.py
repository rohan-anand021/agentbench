from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class EventType(StrEnum):
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_FINISHED = "tool_call_finished"
    AGENT_TURN_STARTED = "agent_turn_started"
    AGENT_TURN_FINISHED = "agent_turn_finished"
    AGENT_FINISHED = "agent_finished"
    PATCH_APPLIED = "patch_applied"
    TESTS_STARTED = "tests_started"
    TESTS_FINISHED = "tests_finished"
    # Command events (for non-test shell commands)
    COMMAND_STARTED = "command_started"
    COMMAND_FINISHED = "command_finished"
    TASK_STARTED = "task_started"
    TASK_FINISHED = "task_finished"

class Event(BaseModel):
    event_type: EventType
    timestamp: datetime
    run_id: str
    step_id: int
    payload: dict[str, Any]
