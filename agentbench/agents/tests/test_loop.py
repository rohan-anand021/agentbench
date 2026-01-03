from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.agents.base import Agent
from agentbench.agents.loop import AgentLoop
from agentbench.agents.types import (
    AgentAction,
    AgentBudget,
    AgentDecision,
    StopReason,
)
from agentbench.tasks.models import EnvironmentSpec, RepoSpec, RunSpec, SetupSpec, TaskSpec
from agentbench.tools.contract import (
    ToolError,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)


class DummyEventLogger:
    def __init__(self, run_id: str = "01TEST"):
        self.run_id = run_id

    def log_tool_started(self, request): pass
    def log_tool_finished(self, result): pass
    def log_patch_applied(self, step_id, changed_files, patch_artifact_path): pass
    def log_tests_started(self, command): pass
    def log_tests_finished(self, exit_code, passed, stdout_path=None, stderr_path=None): pass


class SequenceAgent(Agent):
    def __init__(self, actions):
        super().__init__(config=None)
        self._actions = list(actions)
        self._idx = 0

    @property
    def variant_name(self) -> str:
        return "test"

    def decide(self, state):
        if self._idx < len(self._actions):
            action = self._actions[self._idx]
            self._idx += 1
            return action
        return AgentAction(
            decision=AgentDecision.STOP,
            stop_reason=StopReason.AGENT_GAVE_UP,
        )

    def format_observation(self, state):
        return "obs"


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


def make_tool_request(tool: ToolName, params: dict, request_id: str = "req-1"):
    return ToolRequest(tool=tool, params=params, request_id=request_id)


def make_tool_result(
    request_id: str,
    tool: ToolName,
    status: ToolStatus,
    error: ToolError | None = None,
    exit_code: int | None = None,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
    data: dict | None = None,
):
    now = datetime.now(timezone.utc)
    return ToolResult(
        request_id=request_id,
        tool=tool,
        status=status,
        started_at=now,
        ended_at=now,
        duration_sec=0.01,
        data=data,
        error=error,
        exit_code=exit_code,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def make_sandbox(exit_code: int, stdout: str = "", stderr: str = ""):
    def _run(workspace_host_path, command, network, timeout_sec, stdout_path, stderr_path):
        stdout_path.write_text(stdout, encoding="utf-8", newline="\n")
        stderr_path.write_text(stderr, encoding="utf-8", newline="\n")
        return SimpleNamespace(
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            docker_cmd=[],
        )

    return SimpleNamespace(run=_run)


def test_initial_tests_pass_short_circuits(tmp_path: Path):
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    repo = workspace / "repo"
    repo.mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    agent = SequenceAgent([])
    sandbox = make_sandbox(exit_code=0, stdout="ok")
    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.success is True
    assert result.stop_reason == StopReason.SUCCESS
    assert result.steps_taken == 0
    assert result.final_test_passed is True


def test_stop_on_max_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    request = make_tool_request(ToolName.LIST_FILES, {"root": "."})
    agent = SequenceAgent([AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=request)])
    sandbox = make_sandbox(exit_code=1, stderr="fail")
    budget = AgentBudget(max_steps=1)

    def stub_list_files(request_id, workspace_root, params):
        return make_tool_result(
            request_id=request_id,
            tool=ToolName.LIST_FILES,
            status=ToolStatus.SUCCESS,
            data={"files": []},
        )

    monkeypatch.setattr("agentbench.agents.loop.list_files", stub_list_files)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
        budget=budget,
    )

    result = loop.run()

    assert result.success is False
    assert result.stop_reason == StopReason.MAX_STEPS
    assert result.steps_taken == 1


def test_tool_call_list_files_advances_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    request = make_tool_request(ToolName.LIST_FILES, {"root": "."})
    actions = [
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=request),
        AgentAction(decision=AgentDecision.STOP, stop_reason=StopReason.AGENT_GAVE_UP),
    ]
    agent = SequenceAgent(actions)
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    def stub_list_files(request_id, workspace_root, params):
        return make_tool_result(
            request_id=request_id,
            tool=ToolName.LIST_FILES,
            status=ToolStatus.SUCCESS,
            data={"files": []},
        )

    monkeypatch.setattr("agentbench.agents.loop.list_files", stub_list_files)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.stop_reason == StopReason.AGENT_GAVE_UP
    assert result.steps_taken == 1


def test_tool_error_for_non_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    request = make_tool_request(ToolName.LIST_FILES, {"root": "."})
    agent = SequenceAgent([AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=request)])
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    def stub_list_files(request_id, workspace_root, params):
        return make_tool_result(
            request_id=request_id,
            tool=ToolName.LIST_FILES,
            status=ToolStatus.ERROR,
            error=ToolError(error_type="path_escape", message="bad", details={}),
        )

    monkeypatch.setattr("agentbench.agents.loop.list_files", stub_list_files)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.stop_reason == StopReason.TOOL_ERROR
    assert result.steps_taken == 1


def test_run_tool_error_expected_failure_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    run_request = make_tool_request(ToolName.RUN, {"command": "pytest -q"})
    actions = [
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=run_request),
        AgentAction(decision=AgentDecision.STOP, stop_reason=StopReason.AGENT_GAVE_UP),
    ]
    agent = SequenceAgent(actions)
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    def stub_run_tool(workspace_root, params, sandbox, step_id, artifacts_dir):
        logs_dir = Path(artifacts_dir) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = logs_dir / f"tool_step_{step_id:04d}_stdout.txt"
        stdout_path.write_text("fail", encoding="utf-8", newline="\n")
        return make_tool_result(
            request_id=f"tool_step_{step_id:04d}",
            tool=ToolName.RUN,
            status=ToolStatus.ERROR,
            error=ToolError(error_type="abnormal_exit", message="fail", details={}),
            exit_code=1,
            stdout_path=str(stdout_path),
            stderr_path=None,
        )

    monkeypatch.setattr("agentbench.agents.loop.run_tool", stub_run_tool)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.stop_reason == StopReason.AGENT_GAVE_UP
    assert result.steps_taken == 1
    assert result.final_test_exit_code == 1


def test_repeated_failure_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    run_request = make_tool_request(ToolName.RUN, {"command": "pytest -q"})
    actions = [
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=run_request),
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=run_request),
    ]
    agent = SequenceAgent(actions)
    sandbox = make_sandbox(exit_code=1, stderr="fail")
    budget = AgentBudget(repeated_failure_threshold=2, max_steps=5)

    def stub_run_tool(workspace_root, params, sandbox, step_id, artifacts_dir):
        logs_dir = Path(artifacts_dir) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = logs_dir / f"tool_step_{step_id:04d}_stdout.txt"
        stdout_path.write_text("same failure", encoding="utf-8", newline="\n")
        return make_tool_result(
            request_id=f"tool_step_{step_id:04d}",
            tool=ToolName.RUN,
            status=ToolStatus.ERROR,
            error=ToolError(error_type="abnormal_exit", message="fail", details={}),
            exit_code=1,
            stdout_path=str(stdout_path),
            stderr_path=None,
        )

    monkeypatch.setattr("agentbench.agents.loop.run_tool", stub_run_tool)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
        budget=budget,
    )

    result = loop.run()

    assert result.stop_reason == StopReason.REPEATED_FAILURE
    assert result.steps_taken == 2


# Additional tests for full coverage


class ErrorAgent(Agent):
    """Agent that raises an exception on decide."""

    def __init__(self):
        super().__init__(config=None)

    @property
    def variant_name(self) -> str:
        return "error"

    def decide(self, state):
        raise RuntimeError("Agent error")

    def format_observation(self, state):
        return "obs"


def test_agent_exception_returns_llm_error(tmp_path: Path):
    """Test lines 114-126: exception in agent.decide returns LLM_ERROR."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    agent = ErrorAgent()
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.success is False
    assert result.stop_reason == StopReason.LLM_ERROR


def test_tool_request_none_returns_tool_error(tmp_path: Path):
    """Test lines 145-157: CALL_TOOL with None tool_request returns TOOL_ERROR."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    # Create action with CALL_TOOL but no tool_request
    agent = SequenceAgent([
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=None),
    ])
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.success is False
    assert result.stop_reason == StopReason.TOOL_ERROR


def test_run_tool_success_returns_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test lines 181-194: successful run returns SUCCESS."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    run_request = make_tool_request(ToolName.RUN, {"command": "pytest -q"})
    agent = SequenceAgent([
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=run_request),
    ])
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    def stub_run_tool(workspace_root, params, sandbox, step_id, artifacts_dir):
        logs_dir = Path(artifacts_dir) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = logs_dir / f"tool_step_{step_id:04d}_stdout.txt"
        stdout_path.write_text("PASSED", encoding="utf-8", newline="\n")
        return make_tool_result(
            request_id=f"tool_step_{step_id:04d}",
            tool=ToolName.RUN,
            status=ToolStatus.SUCCESS,
            exit_code=0,
            stdout_path=str(stdout_path),
            data={"combined_output": "PASSED"},
        )

    monkeypatch.setattr("agentbench.agents.loop.run_tool", stub_run_tool)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.success is True
    assert result.stop_reason == StopReason.SUCCESS
    assert result.final_test_exit_code == 0


def test_read_file_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test lines 238-240: READ_FILE tool execution."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    read_request = make_tool_request(ToolName.READ_FILE, {"path": "src/main.py"})
    agent = SequenceAgent([
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=read_request),
        AgentAction(decision=AgentDecision.STOP, stop_reason=StopReason.AGENT_GAVE_UP),
    ])
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    def stub_read_file(request_id, workspace_root, params):
        return make_tool_result(
            request_id=request_id,
            tool=ToolName.READ_FILE,
            status=ToolStatus.SUCCESS,
            data={"content": "def main(): pass", "total_lines": 1},
        )

    monkeypatch.setattr("agentbench.agents.loop.read_file", stub_read_file)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.stop_reason == StopReason.AGENT_GAVE_UP
    assert result.steps_taken == 1


def test_search_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test lines 241-243: SEARCH tool execution."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    search_request = make_tool_request(ToolName.SEARCH, {"query": "def add"})
    agent = SequenceAgent([
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=search_request),
        AgentAction(decision=AgentDecision.STOP, stop_reason=StopReason.AGENT_GAVE_UP),
    ])
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    def stub_search(request_id, workspace_root, params):
        return make_tool_result(
            request_id=request_id,
            tool=ToolName.SEARCH,
            status=ToolStatus.SUCCESS,
            data={"matches": [], "total_matches": 0},
        )

    monkeypatch.setattr("agentbench.agents.loop.search", stub_search)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.stop_reason == StopReason.AGENT_GAVE_UP


def test_apply_patch_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test lines 244-259: APPLY_PATCH tool execution with success."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    patch_request = make_tool_request(
        ToolName.APPLY_PATCH,
        {"unified_diff": "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"},
    )
    agent = SequenceAgent([
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=patch_request),
        AgentAction(decision=AgentDecision.STOP, stop_reason=StopReason.AGENT_GAVE_UP),
    ])
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    def stub_apply_patch(workspace_root, params, step_id, artifacts_dir):
        now = datetime.now(timezone.utc)
        return ToolResult(
            request_id=f"step_{step_id:04d}",
            tool=ToolName.APPLY_PATCH,
            status=ToolStatus.SUCCESS,
            started_at=now,
            ended_at=now,
            duration_sec=0.01,
            data={"changed_files": ["file.py"]},
        )

    monkeypatch.setattr("agentbench.agents.loop.apply_patch", stub_apply_patch)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.stop_reason == StopReason.AGENT_GAVE_UP
    assert len(result.patches_applied) == 1


def test_tool_execution_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test lines 286-300: exception during tool execution."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    list_request = make_tool_request(ToolName.LIST_FILES, {"root": "."})
    agent = SequenceAgent([
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=list_request),
    ])
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    def stub_list_files(request_id, workspace_root, params):
        raise ValueError("Test exception")

    monkeypatch.setattr("agentbench.agents.loop.list_files", stub_list_files)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    # Exception in tool leads to TOOL_ERROR
    assert result.stop_reason == StopReason.TOOL_ERROR


def test_check_stop_conditions_max_time(tmp_path: Path):
    """Test line 310-311: _check_stop_conditions returns MAX_TIME when budget_remaining_sec <= 0."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    agent = SequenceAgent([])
    sandbox = make_sandbox(exit_code=1, stderr="fail")
    budget = AgentBudget(max_time_sec=60, max_steps=10)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
        budget=budget,
    )

    # Create a state with exhausted time budget
    from agentbench.agents.types import AgentState
    state = AgentState(
        run_id="test",
        task_id="task-1",
        step_number=1,
        started_at=datetime.now(timezone.utc),
        tool_history=[],
        patches_applied=[],
        last_test_exit_code=1,
        last_test_output="fail",
        budget_remaining_steps=5,
        budget_remaining_sec=0.0,  # Time exhausted
    )

    reason = loop._check_stop_conditions(state)
    assert reason == StopReason.MAX_TIME


def test_run_tool_reads_output_when_not_in_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test lines 362-369: read output from file when not in data."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    run_request = make_tool_request(ToolName.RUN, {"command": "echo hello"})
    agent = SequenceAgent([
        AgentAction(decision=AgentDecision.CALL_TOOL, tool_request=run_request),
        AgentAction(decision=AgentDecision.STOP, stop_reason=StopReason.AGENT_GAVE_UP),
    ])
    sandbox = make_sandbox(exit_code=1, stderr="fail")

    def stub_run_tool(workspace_root, params, sandbox, step_id, artifacts_dir):
        logs_dir = Path(artifacts_dir) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = logs_dir / f"tool_step_{step_id:04d}_stdout.txt"
        stdout_path.write_text("hello from file", encoding="utf-8", newline="\n")
        # Return result without combined_output in data
        return make_tool_result(
            request_id=f"tool_step_{step_id:04d}",
            tool=ToolName.RUN,
            status=ToolStatus.SUCCESS,
            exit_code=1,
            stdout_path=str(stdout_path),
            data={},  # No combined_output
        )

    monkeypatch.setattr("agentbench.agents.loop.run_tool", stub_run_tool)

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    result = loop.run()

    assert result.stop_reason == StopReason.AGENT_GAVE_UP


def test_workspace_without_repo_subdir(tmp_path: Path):
    """Test lines 54-58: workspace without repo subdir uses workspace as repo_root."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)  # No "repo" subdir
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    agent = SequenceAgent([])
    sandbox = make_sandbox(exit_code=0, stdout="ok")

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    # repo_root should equal workspace_root when no "repo" subdir exists
    assert loop.repo_root == loop.workspace_root

    result = loop.run()
    assert result.success is True


def test_read_and_truncate_output_missing_file(tmp_path: Path):
    """Test lines 395-396: OSError when reading file is handled."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    agent = SequenceAgent([])
    sandbox = make_sandbox(exit_code=0, stdout="ok")

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    # Try to read from non-existent file
    result = loop._read_and_truncate_output(
        tmp_path / "nonexistent.txt",
        None,
    )

    assert result == ""


def test_read_and_truncate_output_empty_content(tmp_path: Path):
    """Test lines 399-400: empty combined content returns empty string."""
    task = make_task(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "repo").mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    agent = SequenceAgent([])
    sandbox = make_sandbox(exit_code=0, stdout="ok")

    loop = AgentLoop(
        agent=agent,
        task=task,
        workspace_root=workspace,
        artifacts_dir=artifacts,
        sandbox=sandbox,
        event_logger=DummyEventLogger(),
    )

    # Create empty files
    empty1 = tmp_path / "empty1.txt"
    empty2 = tmp_path / "empty2.txt"
    empty1.write_text("", encoding="utf-8")
    empty2.write_text("", encoding="utf-8")

    result = loop._read_and_truncate_output(empty1, empty2)

    assert result == ""
