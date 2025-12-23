from pathlib import Path
from datetime import datetime, timezone

from agentbench.schemas.events import Event, EventType
from agentbench.util.jsonl import append_jsonl
from agentbench.tools.contract import ToolRequest, ToolResult


class EventLogger:
    """Logs events to events.jsonl during an agent run."""

    def __init__(self, run_id: str, events_file: Path):
        self.run_id = run_id
        self.events_file = events_file
        self._step_counter = 0

    def next_step_id(self) -> int:
        self._step_counter += 1
        return self._step_counter

    def log(self, event_type: EventType, payload: dict) -> None:
        event = Event(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            run_id=self.run_id,
            step_id=self.next_step_id(),
            payload=payload,
        )

        append_jsonl(self.events_file, event.model_dump(mode="json"))

    def log_tool_started(self, request: ToolRequest) -> None:
        """Log when a tool call begins."""
        self.log(
            event_type=EventType.TOOL_CALL_STARTED,
            payload={
                "request_id": request.request_id,
                "tool": request.tool,
                "params": request.params,
            },
        )

    def log_tool_finished(self, result: ToolResult) -> None:
        """Log when a tool call completes."""
        payload = {
            "request_id": result.request_id,
            "tool": result.tool,
            "status": result.status,
            "duration_sec": result.duration_sec,
        }
        if result.error:
            payload["error"] = result.error.model_dump(mode="json")
        self.log(event_type=EventType.TOOL_CALL_FINISHED, payload=payload)

    def log_agent_turn_started(self) -> None:
        """Log when an agent turn begins."""
        self.log(event_type=EventType.AGENT_TURN_STARTED, payload={})

    def log_agent_turn_finished(self, stopped_reason: str) -> None:
        """Log when an agent turn completes."""
        self.log(
            event_type=EventType.AGENT_TURN_FINISHED,
            payload={"stopped_reason": stopped_reason},
        )

    def log_patch_applied(
        self, step_id: int, changed_files: list[str], patch_artifact_path: str
    ) -> None:
        """Log when a patch is successfully applied."""
        self.log(
            event_type=EventType.PATCH_APPLIED,
            payload={
                "step_id": step_id,
                "changed_files": changed_files,
                "patch_artifact_path": patch_artifact_path,
            },
        )

    def log_tests_started(self, command: str) -> None:
        """Log when test execution begins."""
        self.log(event_type=EventType.TESTS_STARTED, payload={"command": command})

    def log_tests_finished(
        self,
        exit_code: int,
        passed: bool,
        stdout_path: str | None = None,
        stderr_path: str | None = None,
    ) -> None:
        """Log when test execution completes."""
        self.log(
            event_type=EventType.TESTS_FINISHED,
            payload={
                "exit_code": exit_code,
                "passed": passed,
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
            },
        )
