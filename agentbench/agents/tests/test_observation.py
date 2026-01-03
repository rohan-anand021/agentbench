from datetime import datetime, timezone

from agentbench.agents.observation import (
    ObservationContext,
    TestFailureSummary,
    build_observation,
    extract_file_hints,
    format_tool_result_summary,
    parse_test_output,
    truncate_output,
)
from agentbench.agents.types import AgentState
from agentbench.tools.contract import ToolName, ToolRequest, ToolResult, ToolStatus


def make_tool_request(tool: ToolName, params: dict[str, object] | None = None) -> ToolRequest:
    return ToolRequest(
        tool=tool,
        params=params or {},
        request_id=f"req-{tool.value}",
    )


def make_tool_result(
    tool: ToolName,
    status: ToolStatus = ToolStatus.SUCCESS,
    data: dict[str, object] | None = None,
    exit_code: int | None = None,
) -> ToolResult:
    now = datetime.now(timezone.utc)
    return ToolResult(
        request_id=f"req-{tool.value}",
        tool=tool,
        status=status,
        started_at=now,
        ended_at=now,
        duration_sec=0.01,
        data=data,
        exit_code=exit_code,
    )


def make_state(
    tool_history: list[tuple[ToolRequest, ToolResult]] | None = None,
    last_test_output: str | None = None,
    last_test_exit_code: int | None = 1,
) -> AgentState:
    return AgentState(
        run_id="run-1",
        task_id="task-1",
        step_number=2,
        started_at=datetime.now(timezone.utc),
        tool_history=tool_history or [],
        patches_applied=[],
        last_test_exit_code=last_test_exit_code,
        last_test_output=last_test_output,
        budget_remaining_steps=5,
        budget_remaining_sec=120.0,
    )


def test_failure_summary_defaults():
    summary = TestFailureSummary(exit_code=1)

    assert summary.exit_code == 1
    assert summary.failed_test_count is None
    assert summary.failed_tests == []
    assert summary.error_snippets == []
    assert summary.suggested_files == []


def test_observation_context_defaults():
    summary = TestFailureSummary(exit_code=1)
    context = ObservationContext(
        task_description="Fix add()",
        test_command="pytest -q",
        failure_summary=summary,
    )

    assert context.task_description == "Fix add()"
    assert context.test_command == "pytest -q"
    assert context.failure_summary.exit_code == 1
    assert context.recent_tool_results == []
    assert context.file_context == {}
    assert context.budget_info == ""
    assert context.attempt_history == ""


def test_observation_context_with_tool_results():
    summary = TestFailureSummary(exit_code=1)
    tool_result = make_tool_result(ToolName.LIST_FILES, data={"files": ["src/main.py"]})
    context = ObservationContext(
        task_description="Fix add()",
        test_command="pytest -q",
        failure_summary=summary,
        recent_tool_results=[tool_result],
        file_context={"src/main.py": "print('hello')"},
        budget_info="Steps remaining: 5",
        attempt_history="Tried reading files",
    )

    assert context.recent_tool_results[0].tool == ToolName.LIST_FILES
    assert context.file_context["src/main.py"] == "print('hello')"
    assert context.budget_info == "Steps remaining: 5"
    assert context.attempt_history == "Tried reading files"


def test_parse_pytest_failure():
    output = """
============================= test session starts =============================
collected 1 item

tests/test_math.py::test_add FAILED                                   [100%]

=================================== FAILURES ===================================
___________________________________ test_add ___________________________________
>       assert add(1, 1) == 3
E       AssertionError: assert 2 == 3

tests/test_math.py:10: AssertionError
=========================== short test summary info ============================
FAILED tests/test_math.py::test_add - AssertionError: assert 2 == 3
============================== 1 failed in 0.12s ===============================
""".strip()
    summary = parse_test_output(output, exit_code=1)

    assert summary.exit_code == 1
    assert summary.failed_test_count == 1
    assert summary.failed_tests == ["tests/test_math.py::test_add"]
    assert any("AssertionError" in snippet for snippet in summary.error_snippets)
    assert "tests/test_math.py" in summary.suggested_files


def test_parse_pytest_multiple_failures():
    output = """
FAILED tests/test_alpha.py::test_one - AssertionError: boom
FAILED tests/test_beta.py::test_two - ValueError: nope
FAILED tests/test_gamma.py::test_three - TypeError: nope
""".strip()
    summary = parse_test_output(output, exit_code=1)

    assert summary.failed_test_count == 3
    assert summary.failed_tests == [
        "tests/test_alpha.py::test_one",
        "tests/test_beta.py::test_two",
        "tests/test_gamma.py::test_three",
    ]


def test_parse_pytest_error():
    output = """
==================================== ERRORS ====================================
_____________________ ERROR collecting tests/test_bad.py _______________________
ImportError while importing test module 'tests/test_bad.py'.
E   ModuleNotFoundError: No module named 'missing'
=========================== short test summary info ============================
ERROR tests/test_bad.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!
""".strip()
    summary = parse_test_output(output, exit_code=2)

    assert summary.exit_code == 2
    assert summary.failed_test_count == 1
    assert summary.failed_tests == ["tests/test_bad.py"]
    assert any("ModuleNotFoundError" in snippet for snippet in summary.error_snippets)
    assert "tests/test_bad.py" in summary.suggested_files


def test_extract_file_hints_from_traceback():
    summary = TestFailureSummary(
        exit_code=1,
        failed_tests=["tests/test_alpha.py::test_one"],
        suggested_files=["src/alpha.py", "tests/test_alpha.py"],
    )
    hints = extract_file_hints(summary)

    assert hints == ["tests/test_alpha.py", "src/alpha.py"]


def test_truncate_output_short():
    content = "\n".join(f"line {i}" for i in range(50))
    truncated, was_truncated = truncate_output(content, max_lines=100)

    assert truncated == content
    assert was_truncated is False


def test_truncate_output_long():
    content = "\n".join(f"line {i}" for i in range(500))
    truncated, was_truncated = truncate_output(
        content,
        max_lines=100,
        keep_head=2,
        keep_tail=2,
    )

    assert was_truncated is True
    assert "line 0" in truncated
    assert "line 499" in truncated
    assert "[truncated]" in truncated


def test_format_tool_result_list_files():
    result = make_tool_result(ToolName.LIST_FILES, data={"files": ["a.py", "b.py"]})
    summary = format_tool_result_summary(result)

    assert summary.startswith("list_files")
    assert "2 files found" in summary


def test_format_tool_result_apply_patch():
    result = make_tool_result(
        ToolName.APPLY_PATCH,
        data={"changed_files": ["src/main.py"]},
    )
    summary = format_tool_result_summary(result)

    assert summary.startswith("apply_patch")
    assert "changed ['src/main.py']" in summary


def test_format_tool_result_read_file():
    result = make_tool_result(
        ToolName.READ_FILE,
        data={"total_lines": 12},
    )
    summary = format_tool_result_summary(result)

    assert summary.startswith("read_file")
    assert "12 lines" in summary


def test_format_tool_result_search():
    result = make_tool_result(
        ToolName.SEARCH,
        data={"total_matches": 4},
    )
    summary = format_tool_result_summary(result)

    assert summary.startswith("search")
    assert "4 matches" in summary


def test_format_tool_result_run():
    result = make_tool_result(
        ToolName.RUN,
        data={},
        exit_code=1,
    )
    summary = format_tool_result_summary(result)

    assert summary.startswith("run")
    assert "exit_code=1" in summary


def test_format_tool_result_error():
    result = make_tool_result(
        ToolName.APPLY_PATCH,
        status=ToolStatus.ERROR,
    )
    summary = format_tool_result_summary(result)

    assert summary.startswith("apply_patch")
    assert "ERROR (error)" in summary


def test_build_observation_includes_all_sections():
    tool_history = [
        (
            make_tool_request(ToolName.LIST_FILES, {"root": "."}),
            make_tool_result(ToolName.LIST_FILES, data={"files": ["src/main.py"]}),
        ),
        (
            make_tool_request(ToolName.READ_FILE, {"path": "src/main.py"}),
            make_tool_result(
                ToolName.READ_FILE,
                data={"content": "def add(a, b):\n    return a + b\n", "total_lines": 2},
            ),
        ),
    ]
    state = make_state(
        tool_history=tool_history,
        last_test_output="FAILED tests/test_math.py::test_add - AssertionError",
        last_test_exit_code=1,
    )

    observation = build_observation(
        state,
        task_description="Fix add() in src/main.py",
        test_command="pytest -q",
    )

    assert "## Task" in observation
    assert "## Current Status" in observation
    assert "## Test Failure Summary" in observation
    assert "## Suggested Files to Investigate" in observation
    assert "## Recent Actions" in observation
    assert "## Available Tools" in observation
    assert "## Instructions" in observation
    assert "## File Context" in observation
    assert "### src/main.py" in observation


def test_build_observation_respects_budget():
    large_content = "\n".join(f"line {i}" for i in range(1000))
    tool_history = [
        (
            make_tool_request(ToolName.READ_FILE, {"path": "src/large.py"}),
            make_tool_result(
                ToolName.READ_FILE,
                data={"content": large_content, "total_lines": 1000},
            ),
        ),
    ]
    state = make_state(
        tool_history=tool_history,
        last_test_output="FAILED tests/test_large.py::test_big - AssertionError",
        last_test_exit_code=1,
    )

    observation = build_observation(
        state,
        task_description="Fix big output",
        test_command="pytest -q",
        max_context_chars=300,
    )

    context_section = observation.split("## File Context")[1].split("## Available Tools")[0]
    context_body = context_section.strip()

    assert len(context_body) <= 300
    assert "[truncated]" in context_body
