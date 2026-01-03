import json
from datetime import datetime, timezone

from agentbench.agents.llm_v0 import LLMAgentV0
from agentbench.agents.types import AgentDecision, AgentState, StopReason
from agentbench.llm.config import LLMConfig, LLMProvider, ProviderConfig
from agentbench.llm.messages import InputMessage, LLMResponse, MessageRole
from agentbench.tools.contract import ToolName


class StubLLMClient:
    def __init__(self, response: LLMResponse):
        self.response = response
        self.calls = []

    async def complete(self, input_items, tools=None):
        self.calls.append({"input": input_items, "tools": tools})
        return self.response

    def count_tokens(self, input_items):
        return 0


def make_agent(response: LLMResponse) -> LLMAgentV0:
    config = LLMConfig(
        provider_config=ProviderConfig(
            provider=LLMProvider.OPENROUTER,
            model_name="mistralai/devstral-2512:free",
        )
    )
    return LLMAgentV0(config=config, client=StubLLMClient(response))


def make_state() -> AgentState:
    return AgentState(
        run_id="01TEST",
        task_id="toy_fail_pytest",
        step_number=1,
        started_at=datetime.now(timezone.utc),
        tool_history=[],
        patches_applied=[],
        last_test_exit_code=1,
        last_test_output="FAILED tests/test_basic.py::test_add",
        budget_remaining_steps=5,
        budget_remaining_sec=120.0,
    )


def test_decide_returns_tool_request_from_response():
    response = LLMResponse.model_validate(
        {
            "id": "resp-1",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "id": "fc-1",
                    "call_id": "call-1",
                    "name": "search",
                    "arguments": json.dumps({"query": "def add"}),
                }
            ],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = make_state()

    action = agent.decide(state)

    assert action.decision == AgentDecision.CALL_TOOL
    assert action.tool_request is not None
    assert action.tool_request.tool == ToolName.SEARCH
    assert action.tool_request.params["query"] == "def add"


def test_decide_stops_on_text_only_response():
    response = LLMResponse.model_validate(
        {
            "id": "resp-2",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg-1",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "No fix found."}],
                }
            ],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = make_state()

    action = agent.decide(state)

    assert action.decision == AgentDecision.STOP
    assert action.stop_reason == StopReason.AGENT_GAVE_UP
    assert action.reasoning == "No fix found."


def test_decide_stops_on_invalid_arguments():
    response = LLMResponse.model_validate(
        {
            "id": "resp-3",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "id": "fc-2",
                    "call_id": "call-2",
                    "name": "read_file",
                    "arguments": "{not-json}",
                }
            ],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = make_state()

    action = agent.decide(state)

    assert action.decision == AgentDecision.STOP
    assert action.stop_reason == StopReason.LLM_ERROR


def test_llm_response_error_stops():
    response = LLMResponse.model_validate(
        {
            "id": "resp-err",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "failed",
            "output": [],
            "usage": None,
            "error": {"message": "rate limit"},
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = make_state()

    action = agent.decide(state)

    assert action.decision == AgentDecision.STOP
    assert action.stop_reason == StopReason.LLM_ERROR


def test_format_observation_includes_budget_and_test_output():
    response = LLMResponse.model_validate(
        {
            "id": "resp-4",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = make_state()

    obs = agent.format_observation(state)

    assert "Steps remaining: 5" in obs
    assert "Time remaining" in obs
    assert "Last test exit code: 1" in obs
    assert "FAILED tests/test_basic.py::test_add" in obs


def test_build_messages_includes_system_and_user():
    response = LLMResponse.model_validate(
        {
            "id": "resp-5",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    messages = agent._build_messages("obs")

    assert len(messages) == 2
    assert isinstance(messages[0], InputMessage)
    assert messages[0].role == MessageRole.SYSTEM
    assert messages[1].role == MessageRole.USER


# Additional tests for full coverage


def test_variant_name_returns_llm_v0():
    """Test line 35: variant_name property."""
    response = LLMResponse.model_validate(
        {
            "id": "resp-0",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    assert agent.variant_name == "llm_v0"


def test_format_observation_includes_patches_applied():
    """Test lines 59-61: patches_applied are included in observation."""
    response = LLMResponse.model_validate(
        {
            "id": "resp-p",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = AgentState(
        run_id="01TEST",
        task_id="task-1",
        step_number=3,
        started_at=datetime.now(timezone.utc),
        tool_history=[],
        patches_applied=["patch1.diff", "patch2.diff", "patch3.diff"],
        last_test_exit_code=1,
        last_test_output="FAILED",
        budget_remaining_steps=5,
        budget_remaining_sec=100.0,
    )

    obs = agent.format_observation(state)

    assert "Patches applied:" in obs
    assert "patch1.diff" in obs
    assert "patch2.diff" in obs
    assert "patch3.diff" in obs


def test_format_observation_no_test_output():
    """Test observation without last_test_output."""
    response = LLMResponse.model_validate(
        {
            "id": "resp-nt",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = AgentState(
        run_id="01TEST",
        task_id="task-1",
        step_number=0,
        started_at=datetime.now(timezone.utc),
        tool_history=[],
        patches_applied=[],
        last_test_exit_code=None,
        last_test_output=None,
        budget_remaining_steps=10,
        budget_remaining_sec=300.0,
    )

    obs = agent.format_observation(state)

    assert "Last test exit code" not in obs
    assert "Last test output" not in obs


def test_decide_stops_on_unknown_tool():
    """Test lines 177-182: unknown tool name stops with error."""
    response = LLMResponse.model_validate(
        {
            "id": "resp-unknown",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "id": "fc-u",
                    "call_id": "call-u",
                    "name": "unknown_tool",
                    "arguments": "{}",
                }
            ],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = make_state()

    action = agent.decide(state)

    assert action.decision == AgentDecision.STOP
    assert action.stop_reason == StopReason.LLM_ERROR
    assert "Unknown tool: unknown_tool" in action.reasoning


def test_decide_with_dict_tool_call_uses_id_fallback():
    """Test line 160: dict tool_call using 'id' when call_id is used for request_id."""
    response = LLMResponse.model_validate(
        {
            "id": "resp-dict",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "id": "fc-d",
                    "call_id": "call-d",
                    "name": "list_files",
                    "arguments": json.dumps({"root": "."}),
                }
            ],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = make_state()

    action = agent.decide(state)

    assert action.decision == AgentDecision.CALL_TOOL
    assert action.tool_request.tool == ToolName.LIST_FILES
    # call_id is used as request_id
    assert action.tool_request.request_id == "call-d"


def test_decide_with_empty_arguments():
    """Test line 167: empty arguments string."""
    response = LLMResponse.model_validate(
        {
            "id": "resp-empty-args",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "id": "fc-ea",
                    "call_id": "call-ea",
                    "name": "list_files",
                    "arguments": "",
                }
            ],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = make_state()

    action = agent.decide(state)

    assert action.decision == AgentDecision.CALL_TOOL
    assert action.tool_request.params == {}


def test_next_request_id_generation():
    """Test lines 219-221: _next_request_id generates incrementing IDs."""
    response = LLMResponse.model_validate(
        {
            "id": "resp-id-gen",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = make_state()

    # Test ID generation
    id1 = agent._next_request_id(state)
    id2 = agent._next_request_id(state)

    assert id1 == "01TEST-0001-01"
    assert id2 == "01TEST-0001-02"


def test_decide_text_only_empty_text():
    """Test lines 194-196: text-only response with empty text."""
    response = LLMResponse.model_validate(
        {
            "id": "resp-empty-text",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg-e",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": ""}],
                }
            ],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    state = make_state()

    action = agent.decide(state)

    assert action.decision == AgentDecision.STOP
    assert action.stop_reason == StopReason.AGENT_GAVE_UP
    assert action.reasoning == "No tool call returned."


def test_get_tool_definitions_returns_all_tools():
    """Test lines 76-141: tool definitions are returned."""
    response = LLMResponse.model_validate(
        {
            "id": "resp-tools",
            "object": "response",
            "created_at": 123,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [],
            "usage": None,
            "error": None,
            "latency_ms": 0,
        }
    )
    agent = make_agent(response)
    tools = agent._get_tool_definitions()

    assert len(tools) == 5
    tool_names = [t.name for t in tools]
    assert "list_files" in tool_names
    assert "read_file" in tool_names
    assert "search" in tool_names
    assert "apply_patch" in tool_names
    assert "run" in tool_names
