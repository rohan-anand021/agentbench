import logging
from pathlib import Path

from agentbench.agents.base import Agent, AgentResult
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
from agentbench.util.events import EventLogger

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

    def run(
        self,
        _task: TaskSpec,
        sandbox: DockerSandbox,
        workspace_root: Path,
        artifacts_dir: Path,
        _failing_output: str,
    ) -> AgentResult:
        logger.info("Starting scripted agent run %s", self.run_id)
        
        event_logger = EventLogger(
            run_id = self.run_id,
            events_file = artifacts_dir / "events.jsonl"
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
            workspace_root = workspace_root,
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
            params = ReadFileParams(
                path = "src/calculator.py",
                start_line = None,
                end_line = None
            ).model_dump(
                mode = "json"
            ),
            request_id = f"{self.run_id}-002"
        )

        event_logger.log_tool_started(step_2_request)

        step_2_result = read_file(
            request_id = f"{self.run_id}-002",
            workspace_root = workspace_root,
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
            params = SearchParams(
                query = "def add",
                glob = "**/*.py",
            ).model_dump(
                mode = "json"
            ),
            request_id = f"{self.run_id}-003"
        )

        event_logger.log_tool_started(step_3_request)

        step_3_result = search(
            request_id = f"{self.run_id}-003",
            workspace_root = workspace_root,
            params = SearchParams(**step_3_request.params)
        )

        event_logger.log_tool_finished(step_3_result)

        event_logger.log_agent_turn_finished(
            stopped_reason=f"Searched for: {step_3_request.params['query']}"
        )

        logger.debug("Step 4: applying patch")
        event_logger.log_agent_turn_started()

        step_4_request = ToolRequest(
            tool = ToolName.APPLY_PATCH,
            params = ApplyPatchParams(
                unified_diff = """--- a/src/calculator.py
                                  +++ b/src/calculator.py
                                  @@ -1,4 +1,4 @@
                                  def add(a, b):
                                  -    return a - b  # BUG: should be +
                                  +    return a + b
                                """
            ).model_dump(
                mode = "json"
            ),
            request_id = f"{self.run_id}-004"
        )

        event_logger.log_tool_started(step_4_request)

        step_4_result = apply_patch(
            workspace_root = workspace_root,
            params = ApplyPatchParams(**step_4_request.params),
            step_id = 4,
            artifacts_dir = artifacts_dir / "diffs"
        )

        if step_4_result.status == ToolStatus.ERROR:
            logger.error("Patch application failed at step 4")
            return AgentResult(
                success = False,
                stopped_reason = "tool_error",
                steps_taken = 4,
                patch_files = [],
                duration_sec = 0.0
            )
        else:
            event_logger.log_patch_applied(
                step_id = 4,
                changed_files = ["src/calculator.py"],
                patch_artifact_path = str(artifacts_dir / "diffs")
            )

        event_logger.log_tool_finished(step_4_result)

        event_logger.log_agent_turn_finished(
            stopped_reason=f"Applied patch: {step_4_request.params['unified_diff']}"
        )

        logger.debug("Step 5: running tests")
        event_logger.log_agent_turn_started()

        step_5_request = ToolRequest(
            tool = ToolName.RUN,
            params = RunParams(
                command = "pytest -q",
                timeout_sec = 60,
                env = None
            ).model_dump(
                mode = "json"
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
            artifacts_dir = artifacts_dir / "diffs"
        )

        if step_5_result.status == ToolStatus.ERROR:
            logger.error("Test execution failed at step 5")
            return AgentResult(
                success = False,
                stopped_reason = "run_error",
                steps_taken = 5,
                patch_files = [str(artifacts_dir / "diffs" / f"step_{4:04d}.patch")],
                duration_sec = 0.0
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
                stopped_reason = "success",
                steps_taken = 5,
                patch_files = [str(artifacts_dir / "diffs" / f"step_{4:04d}.patch")],
                duration_sec = 0.0,
                exit_code = step_5_result.exit_code
            )
        else:
            logger.warning("Agent run %s failed: tests did not pass", self.run_id)
            event_logger.log_agent_turn_finished(stopped_reason = "tests_failed")
            return AgentResult(
                success = False,
                stopped_reason = "tests_failed",
                steps_taken = 5,
                patch_files = [str(artifacts_dir / "diffs" / f"step_{4:04d}.patch")],
                duration_sec = 0.0
            )




















