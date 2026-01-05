import pytest

from agentbench.agent_runner import map_stop_reason_to_failure
from agentbench.agents.types import StopReason
from agentbench.scoring import FailureReason


@pytest.mark.parametrize(
    "stop_reason,expected",
    [
        (StopReason.SUCCESS, None),
        (StopReason.MAX_STEPS, FailureReason.AGENT_GAVE_UP),
        (StopReason.AGENT_GAVE_UP, FailureReason.AGENT_GAVE_UP),
        (StopReason.REPEATED_FAILURE, FailureReason.AGENT_GAVE_UP),
        (StopReason.MAX_TIME, FailureReason.TIMEOUT),
        (StopReason.TOOL_ERROR, FailureReason.TOOL_ERROR),
        (StopReason.LLM_ERROR, FailureReason.LLM_ERROR),
        (StopReason.INTERRUPTED, FailureReason.INTERRUPTED),
        (None, None),
    ],
)
def test_map_stop_reason_to_failure(stop_reason, expected):
    assert map_stop_reason_to_failure(stop_reason) == expected
