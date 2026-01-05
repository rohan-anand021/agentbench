from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agentbench.agent_runner import map_stop_reason_to_failure, run_agent_attempt
from agentbench.agents.types import AgentResult, StopReason
from agentbench.schemas.attempt_record import AttemptRecord
from agentbench.scoring import FailureReason
from agentbench.tasks.models import AgentSpec, EnvironmentSpec, RepoSpec, RunSpec, SetupSpec, TaskSpec


def make_task(tmp_path: Path) -> TaskSpec:
    return TaskSpec(
        task_spec_version="1.0",
        id="task-1",
        suite="suite",
        repo=RepoSpec(url="https://example.com/repo.git", commit="abc123"),
        environment=EnvironmentSpec(
            docker_image="ghcr.io/agentbench/py-runner:0.1.0",
            workdir="/workspace",
            timeout_sec=10,
        ),
        setup=SetupSpec(commands=[]),
        run=RunSpec(command="pytest -q"),
        validation=None,
        harness_min_version=None,
        labels=None,
        source_path=tmp_path / "task.yaml",
        agent=AgentSpec(entrypoint="scripted", max_steps=5),
    )


def stub_scripted_agent(stop_reason: StopReason):
    class _StubAgent:
        def __init__(self, run_id: str):
            self.run_id = run_id

        @property
        def variant_name(self) -> str:
            return "scripted"

        def run(self, **kwargs) -> AgentResult:
            success = stop_reason == StopReason.SUCCESS
            exit_code = 0 if success else 1
            return AgentResult(
                success=success,
                stop_reason=stop_reason,
                steps_taken=0,
                patches_applied=[],
                duration_sec=0.1,
                final_test_exit_code=exit_code,
                final_test_passed=success,
            )

    return _StubAgent


@pytest.mark.parametrize(
    "stop_reason,expected_failure",
    [
        (StopReason.SUCCESS, None),
        (StopReason.MAX_STEPS, FailureReason.AGENT_GAVE_UP),
        (StopReason.AGENT_GAVE_UP, FailureReason.AGENT_GAVE_UP),
        (StopReason.REPEATED_FAILURE, FailureReason.AGENT_GAVE_UP),
        (StopReason.MAX_TIME, FailureReason.TIMEOUT),
        (StopReason.TOOL_ERROR, FailureReason.TOOL_ERROR),
        (StopReason.LLM_ERROR, FailureReason.LLM_ERROR),
        (StopReason.INTERRUPTED, FailureReason.INTERRUPTED),
    ],
)
def test_attempt_record_failure_reason(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stop_reason, expected_failure):
    """run_agent_attempt should record failure_reason mapped from stop_reason."""
    workspace_dir = tmp_path / "workspace"
    artifacts_dir = tmp_path / "artifacts"
    workspace_dir.mkdir()
    artifacts_dir.mkdir()

    # Patch external dependencies to avoid IO/Docker
    monkeypatch.setattr(
        "agentbench.agent_runner.clone_repo",
        lambda url, dest, logs_dir: (logs_dir / "clone_stdout.txt", logs_dir / "clone_stderr.txt", 0),
    )
    monkeypatch.setattr(
        "agentbench.agent_runner.checkout_commit",
        lambda repo_dir, commit, logs_dir: (logs_dir / "checkout_stdout.txt", logs_dir / "checkout_stderr.txt", 0),
    )
    monkeypatch.setattr(
        "agentbench.agent_runner.DockerSandbox",
        lambda image, workdir: SimpleNamespace(run=lambda **kwargs: MagicMock(exit_code=0, stdout_path=None, stderr_path=None, docker_cmd=[])),
    )

    class DummyEventLogger:
        def __init__(self, run_id, events_file, llm_messages_file, log_llm_messages=None):
            self.run_id = run_id

        def log_agent_finished(self, **kwargs): ...
        def log_tool_started(self, request): ...
        def log_tool_finished(self, result): ...
        def log_patch_applied(self, step_id, changed_files, patch_artifact_path): ...
        def log_tests_started(self, command): ...
        def log_tests_finished(self, exit_code, passed, stdout_path=None, stderr_path=None): ...
        def log_command_started(self, command): ...
        def log_command_finished(self, exit_code, stdout_path=None, stderr_path=None): ...
        def log_event(self, *args, **kwargs): ...

    monkeypatch.setattr("agentbench.agent_runner.EventLogger", DummyEventLogger)

    # Deterministic ULID
    monkeypatch.setattr("agentbench.agent_runner.ulid", SimpleNamespace(ULID=lambda: "01TESTULID"))

    # Stub agent
    monkeypatch.setattr(
        "agentbench.agent_runner.ScriptedAgent",
        stub_scripted_agent(stop_reason),
    )

    task = make_task(tmp_path)
    attempt: AttemptRecord = run_agent_attempt(
        task=task,
        workspace_dir=workspace_dir,
        artifacts_dir=artifacts_dir,
        skip_baseline=True,
    )

    assert attempt.result.stop_reason == stop_reason
    assert attempt.result.failure_reason == expected_failure
    assert attempt.result.exit_code == (0 if stop_reason == StopReason.SUCCESS else 1)
    assert attempt.result.passed == (stop_reason == StopReason.SUCCESS)
