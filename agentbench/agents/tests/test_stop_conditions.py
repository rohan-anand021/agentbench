from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.agents.base import Agent
from agentbench.agents.loop import AgentLoop
from agentbench.agents.types import AgentBudget, AgentState, StopReason
from agentbench.tasks.models import EnvironmentSpec, RepoSpec, RunSpec, SetupSpec, TaskSpec
from agentbench.tools.contract import ToolName, ToolRequest, ToolResult, ToolStatus


class DummyEventLogger:
    def __init__(self, run_id: str = "01TEST"):
        self.run_id = run_id

    def log_tool_started(self, request): pass
    def log_tool_finished(self, result): pass
    def log_patch_applied(self, step_id, changed_files, patch_artifact_path): pass
    def log_tests_started(self, command): pass
    def log_tests_finished(self, exit_code, passed, stdout_path=None, stderr_path=None): pass
    def log_command_started(self, command): pass
    def log_command_finished(self, exit_code, stdout_path=None, stderr_path=None): pass


class NoopAgent(Agent):
    def __init__(self, config=None):
        super().__init__(config=config)

    @property
    def variant_name(self) -> str:
        return "noop"

    def decide(self, state):
        raise NotImplementedError("decide is unused in these tests")

    def format_observation(self, state):
        return ""


def make_task(tmp_path: Path) -> TaskSpec:
    return TaskSpec(
        task_spec_version="1.0",
        id="task-1",
        suite="suite",
        repo=RepoSpec(url="repo", commit="commit"),
        environment=EnvironmentSpec(
            docker_image="ghcr.io/agentbench/py-runner:0.1.0",
            workdir="/workspace",
            timeout_sec=10,
        ),
        setup=SetupSpec(commands=["true"]),
        run=RunSpec(command="pytest -q"),
        validation=None,
        harness_min_version=None,
        labels=None,
        source_path=tmp_path / "task.yaml",
        agent=None,
    )


def make_loop(tmp_path: Path, budget: AgentBudget | None = None) -> AgentLoop:
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    sandbox = SimpleNamespace(run=lambda *args, **kwargs: None)
    agent = NoopAgent(config=None)
    return AgentLoop(
        agent=agent,
        task=make_task(tmp_path),
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
        budget=budget,
    )


def make_state(
    step_number: int,
    last_test_exit_code: int,
    budget_remaining_steps: int,
    budget_remaining_sec: float,
    tool_history=None,
) -> AgentState:
    return AgentState(
        run_id="01TEST",
        task_id="task-1",
        step_number=step_number,
        started_at=datetime.now(timezone.utc),
        tool_history=tool_history or [],
        patches_applied=[],
        last_test_exit_code=last_test_exit_code,
        last_test_output="",
        budget_remaining_steps=budget_remaining_steps,
        budget_remaining_sec=budget_remaining_sec,
        test_command="pytest -q",
    )


def test_success_wins_over_budgets(tmp_path: Path):
    loop = make_loop(tmp_path)
    state = make_state(
        step_number=5,
        last_test_exit_code=0,
        budget_remaining_steps=0,
        budget_remaining_sec=0,
    )
    assert loop._check_stop_conditions(state) == StopReason.SUCCESS


def test_max_steps_checked_before_time(tmp_path: Path):
    loop = make_loop(tmp_path)
    state = make_state(
        step_number=10,
        last_test_exit_code=1,
        budget_remaining_steps=0,
        budget_remaining_sec=0,
    )
    assert loop._check_stop_conditions(state) == StopReason.MAX_STEPS


def test_time_budget_when_steps_remain(tmp_path: Path):
    loop = make_loop(tmp_path)
    state = make_state(
        step_number=3,
        last_test_exit_code=1,
        budget_remaining_steps=2,
        budget_remaining_sec=0.0,
    )
    assert loop._check_stop_conditions(state) == StopReason.MAX_TIME


def test_repeated_failure_detected(tmp_path: Path):
    budget = AgentBudget(repeated_failure_threshold=2, max_steps=5)
    loop = make_loop(tmp_path, budget=budget)

    def run_result(request_id: str) -> ToolResult:
        now = datetime.now(timezone.utc)
        return ToolResult(
            request_id=request_id,
            tool=ToolName.RUN,
            status=ToolStatus.ERROR,
            started_at=now,
            ended_at=now,
            duration_sec=0.01,
            data={"combined_output": "same failure"},
            exit_code=1,
        )

    history = [
        (ToolRequest(tool=ToolName.RUN, params={}, request_id="r1"), run_result("r1")),
        (ToolRequest(tool=ToolName.RUN, params={}, request_id="r2"), run_result("r2")),
    ]

    state = make_state(
        step_number=2,
        last_test_exit_code=1,
        budget_remaining_steps=3,
        budget_remaining_sec=100.0,
        tool_history=history,
    )

    assert loop._check_stop_conditions(state) == StopReason.REPEATED_FAILURE
