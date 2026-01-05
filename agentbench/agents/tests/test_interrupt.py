import pytest

from agentbench.agents.base import Agent
from agentbench.agents.loop import AgentLoop
from agentbench.agents.types import AgentAction, AgentDecision, AgentState, StopReason
from agentbench.tasks.models import (
    AgentSpec,
    EnvironmentSpec,
    RepoSpec,
    RunSpec,
    SetupSpec,
    TaskSpec,
)
from agentbench.util.events import EventLogger, NullEventLogger


class DummyAgent(Agent):
    @property
    def variant_name(self) -> str:
        return "dummy"

    def decide(self, state: AgentState) -> AgentAction:  # pragma: no cover - unused
        return AgentAction(decision=AgentDecision.STOP, stop_reason=StopReason.AGENT_GAVE_UP)

    def format_observation(self, state: AgentState) -> str:  # pragma: no cover - unused
        return ""


def _make_task() -> TaskSpec:
    return TaskSpec(
        task_spec_version="1.0",
        id="dummy",
        suite="dummy",
        repo=RepoSpec(url=".", commit="HEAD"),
        environment=EnvironmentSpec(docker_image="python:3.11-slim", workdir="/workspace", timeout_sec=60),
        setup=SetupSpec(commands=[]),
        run=RunSpec(command="echo"),
        harness_min_version=None,
        labels=[],
        validation=None,
        agent=AgentSpec(entrypoint="llm_v0", max_steps=10),
        source_path=".",
    )


def test_agent_loop_interrupt(monkeypatch, tmp_path):
    task = _make_task()
    agent = DummyAgent()
    event_logger = NullEventLogger()  # not writing files

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=tmp_path,
        artifacts_dir=tmp_path / "artifacts",
        sandbox=None,  # not used due to patch
        event_logger=event_logger,  # type: ignore[arg-type]
        budget=None,
    )

    def _raise_interrupt(started_at):
        raise InterruptedError("simulated SIGINT")

    monkeypatch.setattr(loop, "_run_main", _raise_interrupt)

    result = loop.run()

    assert result.stop_reason == StopReason.INTERRUPTED
    assert result.success is False
    assert result.steps_taken == 0
