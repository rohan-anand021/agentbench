import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from agentbench.schemas.events import Event, EventType
from agentbench.util.jsonl import append_jsonl
from agentbench.tools.contract import ToolRequest, ToolResult

logger = logging.getLogger(__name__)


class EventLogger:
    """Logs events to events.jsonl during an agent run."""

    def __init__(self, run_id: str, events_file: Path, clear_existing: bool = True):
        self.run_id = run_id
        self.events_file = events_file
        self._step_counter = 0
        
        # Clear existing events file at start of new run to avoid accumulation
        if clear_existing and events_file.exists():
            events_file.unlink()
            logger.debug("Cleared existing events file %s", events_file)
        
        logger.debug("EventLogger initialized for run %s, writing to %s", run_id, events_file)

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

        logger.debug("Logged event %s (step %d) for run %s", event_type, event.step_id, self.run_id)
        append_jsonl(self.events_file, event.model_dump_json())

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
            payload["error"] = json.loads(result.error.model_dump_json())
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
        self.log(
            event_type=EventType.TESTS_FINISHED,
            payload={
                "exit_code": exit_code,
                "passed": passed,
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
            },
        )

    def log_command_started(self, command: str) -> None:
        """Log when a non-test shell command begins."""
        self.log(event_type=EventType.COMMAND_STARTED, payload={"command": command})

    def log_command_finished(
        self,
        exit_code: int,
        stdout_path: str | None = None,
        stderr_path: str | None = None,
    ) -> None:
        """Log when a non-test shell command finishes."""
        self.log(
            event_type=EventType.COMMAND_FINISHED,
            payload={
                "exit_code": exit_code,
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
            },
        )

    def log_llm_request_started(
        self,
        model: str,
        message_count: int,
        has_tools: bool,
    ) -> None:
        self.log(
            event_type=EventType.LLM_REQUEST_STARTED,
            payload={
                "model": model,
                "message_count": message_count,
                "has_tools": has_tools,
            },
        )

    def log_llm_request_finished(
        self,
        request_id: str,
        status: str,
        latency_ms: int,
        tokens_used: int,
        has_tool_calls: bool,
    ) -> None:
        self.log(
            event_type=EventType.LLM_REQUEST_FINISHED,
            payload={
                "request_id": request_id,
                "status": status,
                "latency_ms": latency_ms,
                "tokens_used": tokens_used,
                "has_tool_calls": has_tool_calls,
            },
        )

    def log_llm_request_failed(
        self,
        error_type: str,
        message: str,
        retryable: bool,
    ) -> None:
        self.log(
            event_type=EventType.LLM_REQUEST_FAILED,
            payload={
                "error_type": error_type,
                "message": message,
                "retryable": retryable,
            },
        )


class NullEventLogger:
    def log_tool_started(self, request) -> None: pass
    def log_tool_finished(self, result) -> None: pass
    def log_agent_turn_started(self) -> None: pass
    def log_agent_turn_finished(self, stopped_reason: str) -> None: pass
    def log_patch_applied(self, step_id: int, changed_files: list[str], patch_artifact_path: str) -> None: pass
    def log_tests_started(self, command: str) -> None: pass
    def log_tests_finished(self, exit_code: int, passed: bool, stdout_path: str | None = None, stderr_path: str | None = None) -> None: pass
    def log_command_started(self, command: str) -> None: pass
    def log_command_finished(self, exit_code: int, stdout_path: str | None = None, stderr_path: str | None = None) -> None: pass
    def log_llm_request_started(self, model: str, message_count: int, has_tools: bool) -> None: pass
    def log_llm_request_finished(self, request_id: str, status: str, latency_ms: int, tokens_used: int, has_tool_calls: bool) -> None: pass
    def log_llm_request_failed(self, error_type: str, message: str, retryable: bool) -> None: pass


NULL_EVENT_LOGGER = NullEventLogger()
