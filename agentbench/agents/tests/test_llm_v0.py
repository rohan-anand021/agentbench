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
