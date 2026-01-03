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


# Additional tests for full coverage


def test_parse_test_output_empty_returns_default_summary():
    """Test line 58: empty output returns immediately."""
    summary = parse_test_output("", exit_code=1)
    assert summary.exit_code == 1
    assert summary.failed_tests == []
    assert summary.error_snippets == []


def test_parse_unittest_failure_pattern():
    """Test line 74: unittest-style failure parsing."""
    output = """
FAIL: test_add (tests.test_math.TestMath)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tests/test_math.py", line 10, in test_add
    self.assertEqual(add(1, 2), 4)
AssertionError: 3 != 4
""".strip()
    summary = parse_test_output(output, exit_code=1)

    assert "test_add (tests.test_math.TestMath)" in summary.failed_tests


def test_parse_unittest_error_pattern():
    """Test unittest ERROR line parsing."""
    output = """
ERROR: test_div (tests.test_math.TestMath)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tests/test_math.py", line 15, in test_div
    div(1, 0)
ZeroDivisionError: division by zero
""".strip()
    summary = parse_test_output(output, exit_code=1)

    assert "test_div (tests.test_math.TestMath)" in summary.failed_tests


def test_parse_summary_pattern_when_no_failed_tests_pytest():
    """Test lines 94-97: fallback to summary pattern when no failed tests parsed."""
    output = """
==================================== short test summary info ====================================
5 failed, 10 passed in 0.5s
""".strip()
    summary = parse_test_output(output, exit_code=1)

    # No FAILED lines matched, but summary pattern should extract count
    assert summary.failed_test_count == 5


def test_parse_summary_pattern_unittest():
    """Test line 96: unittest summary pattern fallback."""
    # This output has no FAILED lines that match test names, 
    # but has the unittest summary with failure count
    output = """
----------------------------------------------------------------------
Ran 15 tests in 0.100s

failures=3
""".strip()
    summary = parse_test_output(output, exit_code=1)

    # No failed_tests found, so fallback to summary pattern
    assert summary.failed_test_count == 3
    assert summary.failed_tests == []


def test_truncate_output_empty_content():
    """Test line 125: empty content returns immediately."""
    result, was_truncated = truncate_output("")
    assert result == ""
    assert was_truncated is False


def test_truncate_output_very_small_max_chars():
    """Test line 144: max_chars smaller than marker length."""
    content = "a" * 100
    # Marker is about 20 chars, use smaller max
    result, was_truncated = truncate_output(content, max_chars=10)
    assert was_truncated is True
    assert len(result) <= 10


def test_truncate_output_chars_after_line_truncation():
    """Test lines 142-148: char truncation after line truncation."""
    # Create content with many lines
    content = "\n".join(f"{'x' * 100} line {i}" for i in range(200))
    result, was_truncated = truncate_output(
        content,
        max_lines=100,
        max_chars=500,
        keep_head=20,
        keep_tail=20,
    )
    assert was_truncated is True
    assert len(result) <= 500
    assert "[truncated]" in result


def test_format_tool_result_no_data():
    """Test line 160: tool result with no data."""
    result = make_tool_result(ToolName.LIST_FILES, data=None)
    summary = format_tool_result_summary(result)
    assert summary == "list_files → SUCCESS"


def test_format_tool_result_read_file_no_total_lines():
    """Test line 169: read_file with no total_lines in data."""
    result = make_tool_result(ToolName.READ_FILE, data={"content": "hello"})
    summary = format_tool_result_summary(result)
    assert "read_file → read" in summary


def test_format_tool_result_search_no_total_matches():
    """Test line 172: search with no total_matches in data."""
    result = make_tool_result(ToolName.SEARCH, data={"matches": []})
    summary = format_tool_result_summary(result)
    assert "search → searched" in summary


def test_format_tool_result_apply_patch_no_changed_files():
    """Test line 175: apply_patch with empty changed_files."""
    result = make_tool_result(ToolName.APPLY_PATCH, data={"changed_files": []})
    summary = format_tool_result_summary(result)
    assert "apply_patch → patched" in summary


def test_format_tool_result_long_summary_truncated():
    """Test lines 181-182: summary exceeding max_data_chars is truncated."""
    result = make_tool_result(
        ToolName.APPLY_PATCH,
        data={"changed_files": ["file_" + str(i) + ".py" for i in range(100)]},
    )
    summary = format_tool_result_summary(result, max_data_chars=50)
    assert len(summary) <= 50
    assert summary.endswith("...")


def test_build_observation_no_file_context():
    """Test that observation without file context doesn't include File Context section."""
    state = make_state(
        tool_history=[],
        last_test_output="FAILED tests/test.py::test_one",
        last_test_exit_code=1,
    )
    observation = build_observation(
        state,
        task_description="Fix bug",
        test_command="pytest",
    )
    assert "## File Context" not in observation


def test_build_observation_skips_duplicate_paths():
    """Test line 217: duplicate paths are skipped."""
    tool_history = [
        (
            make_tool_request(ToolName.READ_FILE, {"path": "src/main.py"}),
            make_tool_result(
                ToolName.READ_FILE,
                data={"content": "def foo(): pass", "total_lines": 1},
            ),
        ),
        (
            make_tool_request(ToolName.READ_FILE, {"path": "src/main.py"}),
            make_tool_result(
                ToolName.READ_FILE,
                data={"content": "def bar(): pass", "total_lines": 1},
            ),
        ),
    ]
    state = make_state(tool_history=tool_history, last_test_exit_code=1)
    observation = build_observation(state, "Fix", "pytest")
    # Should only appear once
    assert observation.count("### src/main.py") == 1


def test_build_observation_skips_no_path():
    """Test line 216-217: entries with no path are skipped."""
    tool_history = [
        (
            make_tool_request(ToolName.READ_FILE, {}),  # No path
            make_tool_result(
                ToolName.READ_FILE,
                data={"content": "hello"},
            ),
        ),
    ]
    state = make_state(tool_history=tool_history, last_test_exit_code=1)
    observation = build_observation(state, "Fix", "pytest")
    assert "## File Context" not in observation


def test_build_observation_skips_no_content():
    """Test lines 218-219: entries with no content in data are skipped."""
    tool_history = [
        (
            make_tool_request(ToolName.READ_FILE, {"path": "src/empty.py"}),
            make_tool_result(
                ToolName.READ_FILE,
                data={"total_lines": 0},  # No "content" key
            ),
        ),
    ]
    state = make_state(tool_history=tool_history, last_test_exit_code=1)
    observation = build_observation(state, "Fix", "pytest")
    assert "## File Context" not in observation


def test_build_observation_stops_when_budget_exhausted():
    """Test lines 223-224, 227-228: loop stops when remaining budget is exhausted."""
    # Create large content that will exceed remaining budget
    tool_history = [
        (
            make_tool_request(ToolName.READ_FILE, {"path": f"src/file{i}.py"}),
            make_tool_result(
                ToolName.READ_FILE,
                data={"content": "x" * 500, "total_lines": 10},
            ),
        )
        for i in range(10)
    ]
    state = make_state(tool_history=tool_history, last_test_exit_code=1)
    observation = build_observation(state, "Fix", "pytest", max_context_chars=200)
    # Should only include some files due to budget
    assert "## File Context" in observation


def test_build_observation_passing_tests():
    """Test observation shows PASSING when exit code is 0."""
    state = make_state(last_test_exit_code=0)
    observation = build_observation(state, "Task", "pytest")
    assert "PASSING" in observation


def test_extract_file_hints_empty_nodeid():
    """Test that empty file parts are handled correctly."""
    summary = TestFailureSummary(
        exit_code=1,
        failed_tests=["::test_one"],  # Empty file part before ::
        suggested_files=[],
    )
    hints = extract_file_hints(summary)
    # Empty file part should not be added
    assert "" not in hints


def test_format_tool_result_error_with_error_type():
    """Test error result with specific error type."""
    now = datetime.now(timezone.utc)
    from agentbench.tools.contract import ToolError
    result = ToolResult(
        request_id="req-1",
        tool=ToolName.APPLY_PATCH,
        status=ToolStatus.ERROR,
        started_at=now,
        ended_at=now,
        duration_sec=0.01,
        error=ToolError(
            error_type="patch_conflict",
            message="Patch failed to apply",
            details={},
        ),
    )
    summary = format_tool_result_summary(result)
    assert "ERROR (patch_conflict)" in summary


def test_format_tool_result_error_no_error_object():
    """Test error result without error object."""
    now = datetime.now(timezone.utc)
    result = ToolResult(
        request_id="req-1",
        tool=ToolName.APPLY_PATCH,
        status=ToolStatus.ERROR,
        started_at=now,
        ended_at=now,
        duration_sec=0.01,
        error=None,
    )
    summary = format_tool_result_summary(result)
    assert "ERROR (error)" in summary
