from datetime import datetime, timezone

from agentbench.agents.types import (
    AgentAction,
    AgentBudget,
    AgentDecision,
    AgentResult,
    AgentState,
    StopReason,
)
from agentbench.tools.contract import (
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)


def test_stop_reason_values():
    assert {
        StopReason.SUCCESS,
        StopReason.MAX_STEPS,
        StopReason.MAX_TIME,
        StopReason.AGENT_GAVE_UP,
        StopReason.REPEATED_FAILURE,
        StopReason.TOOL_ERROR,
        StopReason.LLM_ERROR,
        StopReason.INTERRUPTED,
    }


def test_agent_decision_values():
    assert {AgentDecision.CALL_TOOL, AgentDecision.STOP}


def test_agent_action_tool_call_serializes():
    request = ToolRequest(
        tool=ToolName.LIST_FILES,
        params={"root": "."},
        request_id="req-1",
    )
    action = AgentAction(
        decision=AgentDecision.CALL_TOOL,
        tool_request=request,
    )

    data = action.model_dump(mode="json")

    assert data["decision"] == AgentDecision.CALL_TOOL
    assert data["tool_request"]["tool"] == ToolName.LIST_FILES
    assert data["tool_request"]["params"]["root"] == "."


def test_agent_action_stop_serializes():
    action = AgentAction(
        decision=AgentDecision.STOP,
        stop_reason=StopReason.AGENT_GAVE_UP,
        reasoning="no progress",
    )

    data = action.model_dump(mode="json")

    assert data["decision"] == AgentDecision.STOP
    assert data["stop_reason"] == StopReason.AGENT_GAVE_UP
    assert data["reasoning"] == "no progress"


def test_agent_state_serialization_round_trip():
    now = datetime.now(timezone.utc)
    request = ToolRequest(
        tool=ToolName.LIST_FILES,
        params={"root": "."},
        request_id="req-1",
    )
    result = ToolResult(
        request_id="req-1",
        tool=ToolName.LIST_FILES,
        status=ToolStatus.SUCCESS,
        started_at=now,
        ended_at=now,
        duration_sec=0.01,
        data={"files": ["src/main.py"]},
    )
    state = AgentState(
        run_id="01TEST",
        task_id="task-1",
        step_number=1,
        started_at=now,
        tool_history=[(request, result)],
        patches_applied=["diffs/step_0001.patch"],
        last_test_exit_code=1,
        last_test_output="FAILED tests/test_basic.py::test_add",
        budget_remaining_steps=3,
        budget_remaining_sec=120.0,
    )

    data = state.model_dump(mode="json")
    restored = AgentState.model_validate(data)

    assert restored.run_id == "01TEST"
    assert restored.tool_history[0][0].tool == ToolName.LIST_FILES
    assert restored.tool_history[0][1].status == ToolStatus.SUCCESS


def test_agent_budget_defaults():
    budget = AgentBudget()
    assert budget.max_steps == 20
    assert budget.max_time_sec == 600
    assert budget.max_patch_attempts == 10
    assert budget.repeated_failure_threshold == 3


def test_budget_step_exhaustion():
    budget = AgentBudget(max_steps=5)
    assert budget.is_step_budget_exhausted(5)
    assert budget.is_step_budget_exhausted(6)
    assert not budget.is_step_budget_exhausted(4)


def test_budget_time_exhaustion():
    budget = AgentBudget(max_time_sec=60)
    assert budget.is_time_budget_exhausted(60)
    assert budget.is_time_budget_exhausted(61)
    assert not budget.is_time_budget_exhausted(59.9)


def test_agent_result_serializes():
    result = AgentResult(
        success=True,
        stop_reason=StopReason.SUCCESS,
        steps_taken=2,
        patches_applied=["diffs/step_0001.patch"],
        duration_sec=1.2,
        final_test_exit_code=0,
        final_test_passed=True,
    )

    data = result.model_dump(mode="json")

    assert data["success"] is True
    assert data["stop_reason"] == StopReason.SUCCESS
