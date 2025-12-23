from agentbench.tools.builtins import read_file
from agentbench.tools.contract import ReadFileParams
from agentbench.tools.contract import ListFilesParams
from agentbench.tools.contract import ToolRequest, ToolName
from pathib import Path
from agentbench.tasks.models import TaskSpec

from agentbench.agents.base import AgentResult
from agentbench.agents.events import EventLogger
from agentbench.agents.base import Agent
from agentbench.tools.builtins import list_files


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

    def run(
        self,
        task: TaskSpec,
        workspace_root: Path,
        artifacts_dir: Path,
        failing_output: str,
    ) -> AgentResult:
        logger = EventLogger(
            run_id = self.run_id,
            events_file = artifacts_dir / "events.jsonl"
        )

        logger.log_agent_turn_started()

        step_1_request = ToolRequest(
            tool = ToolName.LIST_FILES,
            params = {
                "root": ".",
                "glob": "**/*.py"
            },
            request_id = f"{self.run_id}-001"
        )

        logger.log_tool_started(step_1_request)

        step_1_result = list_files(
            request_id = f"{self.run_id}-001",
            workspace_root = workspace_root,
            params = ListFilesParams(
                **step_1_request.params
            )
        )

        logger.log_tool_finished(step_1_result)

        logger.log_agent_turn_finished(stopped_reason="Listed files")

        logger.log_agent_turn_started()

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

        logger.log_tool_started(step_2_request)

        step_2_result = read_file(
            request_id = f"{self.run_id}-002",
            workspace_root = workspace_root,
            params = ReadFileParams(**step_2_request.params)
        )

        logger.log_tool_finished(step_2_result)

        logger.log_agent_turn_finished(
            stopped_reason=f"Read file: {step_2_request.params.path}"
        )

        






