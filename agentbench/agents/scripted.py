import json
import logging
from pathlib import Path

from agentbench.agents.base import Agent
from agentbench.agents.types import AgentAction, AgentResult, AgentState, StopReason
from agentbench.sandbox.docker_sandbox import DockerSandbox
from agentbench.tasks.models import TaskSpec
from agentbench.tools.builtins import list_files, read_file, search, run_tool
from agentbench.tools.contract import (
    ApplyPatchParams,
    ListFilesParams,
    ReadFileParams,
    RunParams,
    SearchParams,
    ToolName,
    ToolRequest,
    ToolStatus,
)
from agentbench.tools.patching import apply_patch
from agentbench.util.commands import normalize_setup_commands
from agentbench.util.events import EventLogger
from agentbench.util.paths import ensure_dir

logger = logging.getLogger(__name__)


class ScriptedAgent(Agent):
    """
    A deterministic scripted agent that follows a fixed sequence.
    This agent is designed to solve toy_fail_pytest by:
    1. Reading the failing test output
    2. Identifying the file to fix (hard-coded for toy task)
    3. Applying a known-good patch
    4. Returning success

    **Fixed sequence for `toy_fail_pytest`:**

    | Step | Tool | Parameters | Purpose |
    |------|------|------------|---------|
    | 1 | `list_files` | `root=".", glob="**/*.py"` | Discover project structure |
    | 2 | `read_file` | `path="src/calculator.py"` | Read the buggy file |
    | 3 | `search` | `query="def add"` | Find the function to fix |
    | 4 | `apply_patch` | (hard-coded fix) | Apply the fix |
    | 5 | `run` | `command="pytest -q"` | Verify fix works |
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        logger.debug("ScriptedAgent initialized with run_id=%s", run_id)

    @property
    def variant_name(self) -> str:
        return "scripted"

    def decide(self, state: AgentState) -> AgentAction:  # pragma: no cover - not used by scripted path
        raise NotImplementedError("ScriptedAgent uses run() directly instead of decide()")

    def format_observation(self, state: AgentState) -> str:  # pragma: no cover - not used by scripted path
        return "ScriptedAgent executes a fixed sequence; observations are not used."

    def run(
        self,
        task: TaskSpec,
        sandbox: DockerSandbox,
        workspace_root: Path,
        artifacts_dir: Path,
        failing_output: str,
    ) -> AgentResult:
        logger.info("Starting scripted agent run %s", self.run_id)

        repo_root = workspace_root / "repo" if (workspace_root / "repo").is_dir() else workspace_root

        event_logger = EventLogger(
            run_id = self.run_id,
            events_file = artifacts_dir / "events.jsonl"
        )

        # Run setup commands so dependencies (pytest, package) are available in the mounted workspace
        if task.setup and task.setup.commands:
            setup_cmd = " && ".join(
                normalize_setup_commands(
                    task.setup.commands,
                    run_command=task.run.command,
                )
            )
            if repo_root != workspace_root:
                setup_cmd = f"cd repo && {setup_cmd}"
            logs_dir = ensure_dir(artifacts_dir / "logs")
            setup_stdout = logs_dir / "setup_stdout.txt"
            setup_stderr = logs_dir / "setup_stderr.txt"
            event_logger.log_command_started(command=setup_cmd)
            setup_timeout = max(task.environment.timeout_sec, 180)
            setup_result = sandbox.run(
                workspace_host_path=workspace_root,
                command=setup_cmd,
                network="bridge",
                timeout_sec=setup_timeout,
                stdout_path=setup_stdout,
                stderr_path=setup_stderr,
            )
            event_logger.log_command_finished(
                exit_code=setup_result.exit_code,
                stdout_path=str(setup_stdout),
                stderr_path=str(setup_stderr),
            )
            if setup_result.exit_code != 0:
                return AgentResult(
                    success=False,
                    stop_reason=StopReason.TOOL_ERROR,
                    steps_taken=0,
                    patches_applied=[],
                    duration_sec=0.0,
                    final_test_exit_code=setup_result.exit_code,
                    final_test_passed=False,
                )

        event_logger.log_agent_turn_started()
        logger.debug("Step 1: listing files")

        step_1_request = ToolRequest(
            tool = ToolName.LIST_FILES,
            params = {
                "root": ".",
                "glob": "**/*.py"
            },
            request_id = f"{self.run_id}-001"
        )

        event_logger.log_tool_started(step_1_request)

        step_1_result = list_files(
            request_id = f"{self.run_id}-001",
            # operate within the repo root so relative paths resolve
            workspace_root = repo_root,
            params = ListFilesParams(
                **step_1_request.params
            )
        )

        event_logger.log_tool_finished(step_1_result)

        event_logger.log_agent_turn_finished(stopped_reason="Listed files")

        logger.debug("Step 2: reading file")
        event_logger.log_agent_turn_started()

        step_2_request = ToolRequest(
            tool = ToolName.READ_FILE,
            params = json.loads(
                ReadFileParams(
                    path = "src/toy/mathy.py",
                    start_line = None,
                    end_line = None
                ).model_dump_json()
            ),
            request_id = f"{self.run_id}-002"
        )

        event_logger.log_tool_started(step_2_request)

        step_2_result = read_file(
            request_id = f"{self.run_id}-002",
            workspace_root = repo_root,
            params = ReadFileParams(**step_2_request.params)
        )

        event_logger.log_tool_finished(step_2_result)

        event_logger.log_agent_turn_finished(
            stopped_reason=f"Read file: {step_2_request.params['path']}"
        )

        logger.debug("Step 3: searching for function")
        event_logger.log_agent_turn_started()

        step_3_request = ToolRequest(
            tool = ToolName.SEARCH,
            params = json.loads(
                SearchParams(
                    query = "def add",
                    glob = "**/*.py",
                ).model_dump_json()
            ),
            request_id = f"{self.run_id}-003"
        )

        event_logger.log_tool_started(step_3_request)

        step_3_result = search(
            request_id = f"{self.run_id}-003",
            workspace_root = repo_root,
            params = SearchParams(**step_3_request.params)
        )

        event_logger.log_tool_finished(step_3_result)

        event_logger.log_agent_turn_finished(
            stopped_reason=f"Searched for: {step_3_request.params['query']}"
        )

        logger.debug("Step 4: applying patch")
        event_logger.log_agent_turn_started()

        diffs_dir = ensure_dir(artifacts_dir / "diffs")

        step_4_request = ToolRequest(
            tool = ToolName.APPLY_PATCH,
            params = json.loads(
                ApplyPatchParams(
                    unified_diff = """--- a/src/toy/mathy.py
+++ b/src/toy/mathy.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""
                ).model_dump_json()
            ),
            request_id = f"{self.run_id}-004"
        )

        event_logger.log_tool_started(step_4_request)

        step_4_result = apply_patch(
            workspace_root = repo_root,
            params = ApplyPatchParams(**step_4_request.params),
            step_id = 4,
            artifacts_dir = diffs_dir
        )

        if step_4_result.status == ToolStatus.ERROR:
            logger.error("Patch application failed at step 4")
            return AgentResult(
                success = False,
                stop_reason = StopReason.TOOL_ERROR,
                steps_taken = 4,
                patches_applied = [],
                duration_sec = 0.0,
                final_test_exit_code = None,
                final_test_passed = False,
            )
        else:
            event_logger.log_patch_applied(
                step_id = 4,
                changed_files = ["src/toy/mathy.py"],
                patch_artifact_path = str(diffs_dir / f"step_{4:04d}.patch")
            )

        event_logger.log_tool_finished(step_4_result)

        event_logger.log_agent_turn_finished(
            stopped_reason=f"Applied patch: {step_4_request.params['unified_diff']}"
        )

        logger.debug("Step 5: running tests")
        event_logger.log_agent_turn_started()

        step_5_request = ToolRequest(
            tool = ToolName.RUN,
            params = json.loads(
                RunParams(
                    command = (
                        "cd repo && PYTHONPATH=/workspace/repo/src:/workspace/site-packages python -m pytest -q"
                    ),
                    timeout_sec = 60,
                    env = None
                ).model_dump_json()
            ),
            request_id = f"{self.run_id}-005"
        )

        event_logger.log_tool_started(step_5_request)
        event_logger.log_tests_started(
            command = "pytest -q"
        )

        step_5_result = run_tool(
            workspace_root = workspace_root,
            params = RunParams(**step_5_request.params),
            sandbox = sandbox,
            step_id = 5,
            artifacts_dir = diffs_dir
        )

        if step_5_result.status == ToolStatus.ERROR:
            logger.error("Test execution failed at step 5")
            return AgentResult(
                success = False,
                stop_reason = StopReason.TOOL_ERROR,
                steps_taken = 5,
                patches_applied = [str(diffs_dir / f"step_{4:04d}.patch")],
                duration_sec = 0.0,
                final_test_exit_code = step_5_result.exit_code,
                final_test_passed = False,
            )

        event_logger.log_tool_finished(step_5_result)

        tests_passed = step_5_result.exit_code == 0

        event_logger.log_tests_finished(
           exit_code = step_5_result.exit_code,
           passed = tests_passed,
           stdout_path = step_5_result.stdout_path,
           stderr_path = step_5_result.stderr_path,
        )

        if tests_passed:
            logger.info("Agent run %s completed successfully", self.run_id)
            event_logger.log_agent_turn_finished(stopped_reason = "success")
            return AgentResult(
                success = True,
                stop_reason = StopReason.SUCCESS,
                steps_taken = 5,
                patches_applied = [str(diffs_dir / f"step_{4:04d}.patch")],
                duration_sec = 0.0,
                final_test_exit_code = step_5_result.exit_code,
                final_test_passed = True,
            )
        else:
            logger.warning("Agent run %s failed: tests did not pass", self.run_id)
            event_logger.log_agent_turn_finished(stopped_reason = "tests_failed")
            return AgentResult(
                success = False,
                stop_reason = StopReason.AGENT_GAVE_UP,
                steps_taken = 5,
                patches_applied = [str(diffs_dir / f"step_{4:04d}.patch")],
                duration_sec = 0.0,
                final_test_exit_code = step_5_result.exit_code,
                final_test_passed = False,
            )






