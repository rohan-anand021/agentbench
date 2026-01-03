from enum import StrEnum
from pydantic import BaseModel, Field
from datetime import datetime

from agentbench.tools.contract import ToolRequest, ToolResult
class StopReason(StrEnum):
    SUCCESS = "SUCCESS"
    MAX_STEPS = "MAX_STEPS"
    MAX_TIME = "MAX_TIME"
    AGENT_GAVE_UP = "AGENT_GAVE_UP"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    TOOL_ERROR = "TOOL_ERROR"
    LLM_ERROR = "LLM_ERROR"
    INTERRUPTED = "INTERRUPTED"


class AgentDecision(StrEnum):
    CALL_TOOL = "CALL_TOOL"
    STOP = "STOP"


class AgentAction(BaseModel):
    decision: AgentDecision
    tool_request: ToolRequest | None = None
    stop_reason: StopReason | None = None
    reasoning: str | None = None


class AgentState(BaseModel):
    run_id: str
    task_id: str
    step_number: int
    started_at: datetime
    tool_history: list[tuple[ToolRequest, ToolResult]] = Field(default_factory=list)
    patches_applied: list[str] = Field(default_factory=list)
    last_test_exit_code: int | None = None
    last_test_output: str | None = None
    budget_remaining_steps: int
    budget_remaining_sec: float
    test_command: str | None = None


class AgentResult(BaseModel):
    success: bool
    stop_reason: StopReason
    steps_taken: int
    patches_applied: list[str] = Field(default_factory=list)
    duration_sec: float
    final_test_exit_code: int | None = None
    final_test_passed: bool

class AgentBudget(BaseModel):
    max_steps: int = Field(default=20, ge=1, le=100)
    max_time_sec: int = Field(default=600, ge=60, le=3600)
    max_patch_attempts: int = Field(default=10, ge=1, le=50)
    repeated_failure_threshold: int = Field(default=3, ge=2, le=10)

    def is_step_budget_exhausted(self, steps_taken: int) -> bool:
        return steps_taken >= self.max_steps

    def is_time_budget_exhausted(self, elapsed_sec: float) -> bool:
        return elapsed_sec >= self.max_time_sec


