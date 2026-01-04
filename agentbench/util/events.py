import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentbench.schemas.events import Event, EventType
from agentbench.util.jsonl import append_jsonl
from agentbench.tools.contract import ToolRequest, ToolResult

logger = logging.getLogger(__name__)


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


class EventLogger:
    """Logs events to events.jsonl during an agent run."""

    def __init__(
        self,
        run_id: str,
        events_file: Path,
        clear_existing: bool = True,
        llm_messages_file: Path | None = None,
        log_llm_messages: bool | None = None,
    ):
        self.run_id = run_id
        self.events_file = events_file
        self.llm_messages_file = llm_messages_file
        self._step_counter = 0
        self._llm_step_counter = 0
        self._log_llm_messages = (
            log_llm_messages
            if log_llm_messages is not None
            else _env_truthy("AGENTBENCH_LOG_LLM_MESSAGES")
        )
        self._llm_log_max_chars = _env_int("AGENTBENCH_LLM_LOG_MAX_CHARS", 20000)
        
        # Clear existing events file at start of new run to avoid accumulation
        if clear_existing and events_file.exists():
            events_file.unlink()
            logger.debug("Cleared existing events file %s", events_file)
        if (
            self._log_llm_messages
            and self.llm_messages_file is not None
            and clear_existing
            and self.llm_messages_file.exists()
        ):
            self.llm_messages_file.unlink()
            logger.debug("Cleared existing LLM messages file %s", self.llm_messages_file)
        
        logger.debug("EventLogger initialized for run %s, writing to %s", run_id, events_file)

    def next_step_id(self) -> int:
        self._step_counter += 1
        return self._step_counter

    def next_llm_step_id(self) -> int:
        self._llm_step_counter += 1
        return self._llm_step_counter

    def _truncate_value(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        max_chars = self._llm_log_max_chars
        if max_chars <= 0 or len(value) <= max_chars:
            return value
        head = max_chars // 2
        tail = max_chars - head
        omitted = len(value) - max_chars
        return (
            f"{value[:head]}\n\n... [{omitted} chars truncated] ...\n\n{value[-tail:]}"
        )

    def _truncate_payload(self, payload: Any) -> Any:
        if payload is None:
            return None
        if isinstance(payload, dict):
            return {k: self._truncate_payload(v) for k, v in payload.items()}
        if isinstance(payload, list):
            return [self._truncate_payload(v) for v in payload]
        return self._truncate_value(payload)

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

    def log_llm_messages(
        self,
        request: dict[str, Any],
        response: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        if not self._log_llm_messages:
            return
        path = self.llm_messages_file or (self.events_file.parent / "llm_messages.jsonl")
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "step_id": self.next_llm_step_id(),
            "record_type": "llm",
            "request": self._truncate_payload(request),
            "response": self._truncate_payload(response) if response is not None else None,
            "error": error,
        }
        append_jsonl(path, payload)

    def _log_llm_tool_result(self, result: ToolResult) -> None:
        if not self._log_llm_messages:
            return
        path = self.llm_messages_file or (self.events_file.parent / "llm_messages.jsonl")
        error_payload = (
            json.loads(result.error.model_dump_json()) if result.error else None
        )
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "step_id": self.next_llm_step_id(),
            "record_type": "tool_result",
            "request_id": result.request_id,
            "tool": result.tool,
            "status": result.status,
            "duration_sec": result.duration_sec,
            "data": self._truncate_payload(result.data) if result.data is not None else None,
            "error": error_payload,
            "exit_code": result.exit_code,
            "stdout_path": result.stdout_path,
            "stderr_path": result.stderr_path,
        }
        append_jsonl(path, payload)

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
        self._log_llm_tool_result(result)

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
    def log_llm_messages(self, request: dict[str, Any], response: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> None: pass


NULL_EVENT_LOGGER = NullEventLogger()
