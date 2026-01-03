from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import ulid

from agentbench.agents.base import Agent
from agentbench.agents.types import (
    AgentAction,
    AgentBudget,
    AgentDecision,
    AgentResult,
    AgentState,
    StopReason,
)
from agentbench.sandbox.docker_sandbox import DockerSandbox
from agentbench.tasks.models import TaskSpec
from agentbench.tools.builtins import list_files, read_file, run_tool, search
from agentbench.tools.contract import (
    ApplyPatchParams,
    ListFilesParams,
    ReadFileParams,
    RunParams,
    SearchParams,
    ToolError,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)
from agentbench.tools.patching import apply_patch
from agentbench.util.events import EventLogger
from agentbench.util.paths import ensure_dir
from agentbench.util.truncation import truncate_output


class AgentLoop:
    """Executes an agent's decision loop with budget enforcement."""

    def __init__(
        self,
        agent: Agent,
        task: TaskSpec,
        workspace_root: Path,
        artifacts_dir: Path,
        sandbox: DockerSandbox,
        event_logger: EventLogger,
        budget: AgentBudget | None = None,
    ):
        self.agent = agent
        self.task = task
        self.workspace_root = Path(workspace_root)
        self.repo_root = (
            self.workspace_root / "repo"
            if (self.workspace_root / "repo").is_dir()
            else self.workspace_root
        )
        self.artifacts_dir = Path(artifacts_dir)
        self.sandbox = sandbox
        self.event_logger = event_logger
        self.budget = budget or AgentBudget()
        self._tool_step_counter = 0

    def run(self) -> AgentResult:
        started_at = datetime.now(timezone.utc)

        exit_code, output = self._run_initial_tests()
        if exit_code == 0:
            duration = (datetime.now(timezone.utc) - started_at).total_seconds()
            return AgentResult(
                success=True,
                stop_reason=StopReason.SUCCESS,
                steps_taken=0,
                patches_applied=[],
                duration_sec=duration,
                final_test_exit_code=exit_code,
                final_test_passed=True,
            )

        state = AgentState(
            run_id=self.event_logger.run_id,
            task_id=self.task.id,
            step_number=0,
            started_at=started_at,
            tool_history=[],
            patches_applied=[],
            last_test_exit_code=exit_code,
            last_test_output=output,
            budget_remaining_steps=self.budget.max_steps,
            budget_remaining_sec=self.budget.max_time_sec,
        )

        while True:
            stop_reason = self._check_stop_conditions(state)
            if stop_reason:
                duration = (
                    datetime.now(timezone.utc) - state.started_at
                ).total_seconds()
                final_exit = state.last_test_exit_code
                final_passed = final_exit == 0 if final_exit is not None else False
                return AgentResult(
                    success=stop_reason == StopReason.SUCCESS,
                    stop_reason=stop_reason,
                    steps_taken=state.step_number,
                    patches_applied=state.patches_applied,
                    duration_sec=duration,
                    final_test_exit_code=final_exit,
                    final_test_passed=final_passed,
                )

            try:
                action = self.agent.decide(state)
            except Exception:
                duration = (
                    datetime.now(timezone.utc) - state.started_at
                ).total_seconds()
                return AgentResult(
                    success=False,
                    stop_reason=StopReason.LLM_ERROR,
                    steps_taken=state.step_number,
                    patches_applied=state.patches_applied,
                    duration_sec=duration,
                    final_test_exit_code=state.last_test_exit_code,
                    final_test_passed=False,
                )

            if action.decision == AgentDecision.STOP:
                reason = action.stop_reason or StopReason.AGENT_GAVE_UP
                duration = (
                    datetime.now(timezone.utc) - state.started_at
                ).total_seconds()
                final_exit = state.last_test_exit_code
                final_passed = final_exit == 0 if final_exit is not None else False
                return AgentResult(
                    success=reason == StopReason.SUCCESS,
                    stop_reason=reason,
                    steps_taken=state.step_number,
                    patches_applied=state.patches_applied,
                    duration_sec=duration,
                    final_test_exit_code=final_exit,
                    final_test_passed=final_passed,
                )

            if action.tool_request is None:
                duration = (
                    datetime.now(timezone.utc) - state.started_at
                ).total_seconds()
                return AgentResult(
                    success=False,
                    stop_reason=StopReason.TOOL_ERROR,
                    steps_taken=state.step_number,
                    patches_applied=state.patches_applied,
                    duration_sec=duration,
                    final_test_exit_code=state.last_test_exit_code,
                    final_test_passed=False,
                )

            result = self._execute_tool(action.tool_request)
            state = self._update_state(state, action, result)
            if result.status == ToolStatus.ERROR:
                is_expected_test_failure = (
                    action.tool_request.tool == ToolName.RUN
                    and result.error is not None
                    and result.error.error_type == "abnormal_exit"
                )
                if not is_expected_test_failure:
                    duration = (
                        datetime.now(timezone.utc) - state.started_at
                    ).total_seconds()
                    return AgentResult(
                        success=False,
                        stop_reason=StopReason.TOOL_ERROR,
                        steps_taken=state.step_number,
                        patches_applied=state.patches_applied,
                        duration_sec=duration,
                        final_test_exit_code=state.last_test_exit_code,
                        final_test_passed=False,
                    )

            if action.tool_request.tool == ToolName.RUN:
                if result.exit_code == 0:
                    duration = (
                        datetime.now(timezone.utc) - state.started_at
                    ).total_seconds()
                    return AgentResult(
                        success=True,
                        stop_reason=StopReason.SUCCESS,
                        steps_taken=state.step_number,
                        patches_applied=state.patches_applied,
                        duration_sec=duration,
                        final_test_exit_code=result.exit_code,
                        final_test_passed=True,
                    )

    def _run_initial_tests(self) -> tuple[int, str]:
        logs_dir = ensure_dir(self.artifacts_dir / "logs")
        stdout_path = logs_dir / "step_0001_stdout.txt"
        stderr_path = logs_dir / "step_0001_stderr.txt"

        command = self.task.run.command
        if self.repo_root != self.workspace_root:
            command = f"cd repo && {command}"

        self.event_logger.log_tests_started(command=command)

        result = self.sandbox.run(
            workspace_host_path=self.workspace_root,
            command=command,
            network="none",
            timeout_sec=self.task.environment.timeout_sec,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

        output = self._read_and_truncate_output(stdout_path, stderr_path)

        self.event_logger.log_tests_finished(
            exit_code=result.exit_code,
            passed=result.exit_code == 0,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
        )

        return result.exit_code, output

    def _execute_tool(self, request: ToolRequest) -> ToolResult:
        self.event_logger.log_tool_started(request)

        self._tool_step_counter += 1
        step_id = self._tool_step_counter
        started_at = datetime.now(timezone.utc)

        try:
            if request.tool == ToolName.LIST_FILES:
                params = ListFilesParams(**request.params)
                result = list_files(request.request_id, self.repo_root, params)
            elif request.tool == ToolName.READ_FILE:
                params = ReadFileParams(**request.params)
                result = read_file(request.request_id, self.repo_root, params)
            elif request.tool == ToolName.SEARCH:
                params = SearchParams(**request.params)
                result = search(request.request_id, self.repo_root, params)
            elif request.tool == ToolName.APPLY_PATCH:
                params = ApplyPatchParams(**request.params)
                diffs_dir = ensure_dir(self.artifacts_dir / "diffs")
                result = apply_patch(self.repo_root, params, step_id, diffs_dir)
                result.request_id = request.request_id
                if result.status == ToolStatus.SUCCESS:
                    patch_path = diffs_dir / f"step_{step_id:04d}.patch"
                    if result.data is None:
                        result.data = {}
                    result.data["patch_path"] = str(patch_path)
                    changed_files = result.data.get("changed_files", [])
                    self.event_logger.log_patch_applied(
                        step_id=step_id,
                        changed_files=changed_files,
                        patch_artifact_path=str(patch_path),
                    )
            elif request.tool == ToolName.RUN:
                params = RunParams(**request.params)
                self.event_logger.log_tests_started(command=params.command)
                result = run_tool(
                    workspace_root=self.repo_root,
                    params=params,
                    sandbox=self.sandbox,
                    step_id=step_id,
                    artifacts_dir=self.artifacts_dir,
                )
                result.request_id = request.request_id
                output = self._read_and_truncate_output(
                    Path(result.stdout_path) if result.stdout_path else None,
                    Path(result.stderr_path) if result.stderr_path else None,
                )
                if result.data is None:
                    result.data = {}
                result.data["combined_output"] = output
                self.event_logger.log_tests_finished(
                    exit_code=result.exit_code or -1,
                    passed=(result.exit_code == 0),
                    stdout_path=result.stdout_path,
                    stderr_path=result.stderr_path,
                )
            else:
                raise ValueError(f"Unknown tool: {request.tool}")
        except Exception as exc:
            ended_at = datetime.now(timezone.utc)
            result = ToolResult(
                request_id=request.request_id,
                tool=request.tool,
                status=ToolStatus.ERROR,
                started_at=started_at,
                ended_at=ended_at,
                duration_sec=(ended_at - started_at).total_seconds(),
                error=ToolError(
                    error_type=type(exc).__name__,
                    message=str(exc),
                    details={},
                ),
            )

        self.event_logger.log_tool_finished(result)
        return result

    def _check_stop_conditions(self, state: AgentState) -> StopReason | None:
        if state.last_test_exit_code == 0:
            return StopReason.SUCCESS
        if state.budget_remaining_steps <= 0:
            return StopReason.MAX_STEPS
        if state.budget_remaining_sec <= 0:
            return StopReason.MAX_TIME

        threshold = self.budget.repeated_failure_threshold
        outputs = []
        for request, result in state.tool_history:
            if request.tool != ToolName.RUN:
                continue
            if not result.data:
                continue
            output = result.data.get("combined_output")
            if output is not None:
                outputs.append(output)

        if len(outputs) >= threshold:
            tail = outputs[-threshold:]
            if tail and all(out == tail[0] for out in tail):
                return StopReason.REPEATED_FAILURE

        return None

    def _update_state(
        self,
        state: AgentState,
        action: AgentAction,
        result: ToolResult | None,
    ) -> AgentState:
        step_number = state.step_number + 1
        budget_remaining_steps = max(0, state.budget_remaining_steps - 1)
        elapsed = (datetime.now(timezone.utc) - state.started_at).total_seconds()
        budget_remaining_sec = max(0.0, self.budget.max_time_sec - elapsed)

        tool_history = list(state.tool_history)
        if action.decision == AgentDecision.CALL_TOOL and result is not None:
            tool_history.append((action.tool_request, result))

        patches_applied = list(state.patches_applied)
        last_test_exit_code = state.last_test_exit_code
        last_test_output = state.last_test_output

        if action.decision == AgentDecision.CALL_TOOL and result is not None:
            if (
                action.tool_request.tool == ToolName.APPLY_PATCH
                and result.status == ToolStatus.SUCCESS
            ):
                if result.data and result.data.get("patch_path"):
                    patches_applied.append(result.data["patch_path"])
            if action.tool_request.tool == ToolName.RUN:
                last_test_exit_code = result.exit_code
                output = None
                if result.data and result.data.get("combined_output"):
                    output = result.data.get("combined_output")
                else:
                    output = self._read_and_truncate_output(
                        Path(result.stdout_path) if result.stdout_path else None,
                        Path(result.stderr_path) if result.stderr_path else None,
                    )
                    if result.data is not None:
                        result.data["combined_output"] = output
                last_test_output = output

        return AgentState(
            run_id=state.run_id,
            task_id=state.task_id,
            step_number=step_number,
            started_at=state.started_at,
            tool_history=tool_history,
            patches_applied=patches_applied,
            last_test_exit_code=last_test_exit_code,
            last_test_output=last_test_output,
            budget_remaining_steps=budget_remaining_steps,
            budget_remaining_sec=budget_remaining_sec,
        )

    def _read_and_truncate_output(
        self,
        stdout_path: Path | None,
        stderr_path: Path | None,
    ) -> str:
        chunks = []
        for path in (stdout_path, stderr_path):
            if path is None:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            chunks.append(content)
        combined = "\n".join(chunks).strip()
        if not combined:
            return ""
        truncated, _ = truncate_output(combined)
        return truncated
