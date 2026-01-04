import json
from datetime import datetime, timezone

from agentbench.tools.contract import ToolName, ToolResult, ToolStatus
from agentbench.util.events import EventLogger
from agentbench.util.jsonl import read_jsonl


def test_log_llm_messages_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTBENCH_LOG_LLM_MESSAGES", raising=False)

    events_path = tmp_path / "events.jsonl"
    llm_path = tmp_path / "llm_messages.jsonl"
    logger = EventLogger(
        run_id="01TEST",
        events_file=events_path,
        llm_messages_file=llm_path,
    )

    logger.log_llm_messages(
        request={"input": "hello"},
        response={"output": "world"},
        error=None,
    )

    assert not llm_path.exists()


def test_log_llm_messages_forced_enabled(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTBENCH_LOG_LLM_MESSAGES", raising=False)

    events_path = tmp_path / "events.jsonl"
    llm_path = tmp_path / "llm_messages.jsonl"
    logger = EventLogger(
        run_id="01TEST",
        events_file=events_path,
        llm_messages_file=llm_path,
        log_llm_messages=True,
    )

    logger.log_llm_messages(
        request={"input": "hello"},
        response={"output": "world"},
        error=None,
    )

    records = list(read_jsonl(llm_path))
    assert len(records) == 1


def test_log_llm_messages_forced_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTBENCH_LOG_LLM_MESSAGES", "1")

    events_path = tmp_path / "events.jsonl"
    llm_path = tmp_path / "llm_messages.jsonl"
    logger = EventLogger(
        run_id="01TEST",
        events_file=events_path,
        llm_messages_file=llm_path,
        log_llm_messages=False,
    )

    logger.log_llm_messages(
        request={"input": "hello"},
        response={"output": "world"},
        error=None,
    )

    assert not llm_path.exists()


def test_log_tool_results_appended(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTBENCH_LOG_LLM_MESSAGES", "1")

    events_path = tmp_path / "events.jsonl"
    llm_path = tmp_path / "llm_messages.jsonl"
    logger = EventLogger(
        run_id="01TEST",
        events_file=events_path,
        llm_messages_file=llm_path,
    )

    now = datetime.now(timezone.utc)
    result = ToolResult(
        request_id="tool-1",
        tool=ToolName.READ_FILE,
        status=ToolStatus.SUCCESS,
        started_at=now,
        ended_at=now,
        duration_sec=0.01,
        data={"content": "ok"},
        error=None,
        exit_code=None,
        stdout_path=None,
        stderr_path=None,
    )

    logger.log_tool_finished(result)

    records = list(read_jsonl(llm_path))
    assert len(records) == 1
    record = records[0]
    assert record["record_type"] == "tool_result"
    assert record["request_id"] == "tool-1"
    assert record["tool"] == ToolName.READ_FILE
    assert record["data"]["content"] == "ok"


def test_log_llm_messages_writes_truncated_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTBENCH_LOG_LLM_MESSAGES", "1")
    monkeypatch.setenv("AGENTBENCH_LLM_LOG_MAX_CHARS", "20")

    events_path = tmp_path / "events.jsonl"
    llm_path = tmp_path / "llm_messages.jsonl"
    logger = EventLogger(
        run_id="01TEST",
        events_file=events_path,
        llm_messages_file=llm_path,
    )

    long_text = "a" * 50
    logger.log_llm_messages(
        request={"payload": long_text},
        response={"content": long_text},
        error={"error_type": "test_error", "message": "boom", "retryable": False},
    )

    records = list(read_jsonl(llm_path))
    assert len(records) == 1

    record = records[0]
    assert record["run_id"] == "01TEST"
    assert record["error"]["error_type"] == "test_error"

    request_payload = record["request"]["payload"]
    response_content = record["response"]["content"]
    assert "... [30 chars truncated] ..." in request_payload
    assert "... [30 chars truncated] ..." in response_content


def test_log_agent_finished_writes_event(tmp_path):
    events_path = tmp_path / "events.jsonl"
    logger = EventLogger(
        run_id="01TEST",
        events_file=events_path,
    )

    logger.log_agent_finished(
        success=False,
        stop_reason="MAX_STEPS",
        steps_taken=5,
        final_test_exit_code=1,
        final_test_passed=False,
        failure_reason="AGENT_GAVE_UP",
    )

    records = list(read_jsonl(events_path))
    assert len(records) == 1
    record = records[0]
    assert record["event_type"] == "agent_finished"
    assert record["payload"]["stop_reason"] == "MAX_STEPS"
    assert record["payload"]["failure_reason"] == "AGENT_GAVE_UP"
