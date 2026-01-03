from dataclasses import dataclass, field
import re

from agentbench.agents.types import AgentState
from agentbench.tools.contract import ToolName, ToolRequest, ToolResult, ToolStatus


@dataclass
class TestFailureSummary:
    __test__ = False
    exit_code: int
    failed_test_count: int | None = None
    failed_tests: list[str] = field(default_factory=list)
    error_snippets: list[str] = field(default_factory=list)
    suggested_files: list[str] = field(default_factory=list)


@dataclass
class ObservationContext:
    __test__ = False
    task_description: str
    test_command: str
    failure_summary: TestFailureSummary
    recent_tool_results: list[ToolResult] = field(default_factory=list)
    file_context: dict[str, str] = field(default_factory=dict)
    budget_info: str = ""
    attempt_history: str = ""


_FAILED_TEST_PATTERN = re.compile(
    r"^(FAILED|ERROR)\s+(.+?)(?:\s+-\s+.*)?$"
)
_UNITTEST_FAIL_PATTERN = re.compile(r"^(FAIL|ERROR):\s+(.+)$")
_TRACEBACK_FILE_PATTERN = re.compile(r'File "([^"]+\.py)"')
_PATH_PATTERN = re.compile(r"([A-Za-z0-9_./-]+\.py)")
_PYTEST_SUMMARY_PATTERN = re.compile(r"(\d+)\s+failed")
_UNITTEST_SUMMARY_PATTERN = re.compile(r"failures=(\d+)")
_ERROR_KEYWORDS = (
    "AssertionError",
    "TypeError",
    "ValueError",
    "AttributeError",
    "KeyError",
    "IndexError",
    "ImportError",
    "ModuleNotFoundError",
    "NameError",
)


def parse_test_output(
    output: str,
    exit_code: int,
    test_framework: str = "pytest",
) -> TestFailureSummary:
    summary = TestFailureSummary(exit_code=exit_code)
    if not output:
        return summary

    failed_tests = []
    error_snippets = []
    suggested_files = []
    lines = output.splitlines()

    for line in lines:
        stripped = line.strip()
        match = _FAILED_TEST_PATTERN.match(stripped)
        if match:
            nodeid = match.group(2).strip()
            failed_tests.append(nodeid)
        else:
            unit_match = _UNITTEST_FAIL_PATTERN.match(stripped)
            if unit_match:
                failed_tests.append(unit_match.group(2).strip())

        if stripped.startswith("E   "):
            error_snippets.append(stripped[4:])
        else:
            for keyword in _ERROR_KEYWORDS:
                if keyword in stripped:
                    error_snippets.append(stripped)
                    break

        for pattern in (_TRACEBACK_FILE_PATTERN, _PATH_PATTERN):
            for path in pattern.findall(stripped):
                if path not in suggested_files:
                    suggested_files.append(path)

    # remove duplicates while preserving order
    summary.failed_tests = list(dict.fromkeys(failed_tests))
    if summary.failed_tests:
        summary.failed_test_count = len(summary.failed_tests)
    else:
        match = _PYTEST_SUMMARY_PATTERN.search(output)
        if not match:
            match = _UNITTEST_SUMMARY_PATTERN.search(output)
        summary.failed_test_count = int(match.group(1)) if match else None
    summary.error_snippets = list(dict.fromkeys(error_snippets))
    summary.suggested_files = suggested_files
    return summary


def extract_file_hints(failure_summary: TestFailureSummary) -> list[str]:
    hints = []
    for nodeid in failure_summary.failed_tests:
        file_part = nodeid.split("::", 1)[0]
        if file_part and file_part not in hints:
            hints.append(file_part)

    for path in failure_summary.suggested_files:
        if path not in hints:
            hints.append(path)

    return hints


def truncate_output(
    content: str,
    max_lines: int = 100,
    max_chars: int = 10000,
    keep_head: int = 40,
    keep_tail: int = 60,
) -> tuple[str, bool]:
    if not content:
        return "", False

    lines = content.splitlines()
    if len(content) <= max_chars and len(lines) <= max_lines:
        return content, False

    truncated = content
    was_truncated = False

    marker = "\n... [truncated] ...\n"

    if len(lines) > max_lines:
        head = lines[:keep_head]
        tail = lines[-keep_tail:] if keep_tail > 0 else []
        truncated = "\n".join(head) + marker + "\n".join(tail)
        was_truncated = True

    if len(truncated) > max_chars:
        if max_chars <= len(marker):
            truncated = marker[:max_chars]
        else:
            keep = (max_chars - len(marker)) // 2
            truncated = truncated[:keep] + marker + truncated[-keep:]
        was_truncated = True

    return truncated, was_truncated


def format_tool_result_summary(result: ToolResult, max_data_chars: int = 500) -> str:
    tool = result.tool.value
    if result.status == ToolStatus.ERROR:
        error = result.error.error_type if result.error else "error"
        return f"{tool} → ERROR ({error})"

    if result.data is None:
        return f"{tool} → SUCCESS"

    data = result.data
    summary = ""
    if result.tool == ToolName.LIST_FILES:
        count = len(data.get("files", []))
        summary = f"{tool} → {count} files found"
    elif result.tool == ToolName.READ_FILE:
        total_lines = data.get("total_lines")
        summary = f"{tool} → {total_lines} lines" if total_lines else f"{tool} → read"
    elif result.tool == ToolName.SEARCH:
        total = data.get("total_matches")
        summary = f"{tool} → {total} matches" if total is not None else f"{tool} → searched"
    elif result.tool == ToolName.APPLY_PATCH:
        changed = data.get("changed_files", [])
        summary = f"{tool} → changed {changed}" if changed else f"{tool} → patched"
    elif result.tool == ToolName.RUN:
        summary = f"{tool} → exit_code={result.exit_code}"
    else:
        summary = f"{tool} → SUCCESS"

    if len(summary) > max_data_chars:
        summary = summary[: max_data_chars - 3] + "..."
    return summary


def build_observation(
    state: AgentState,
    task_description: str,
    test_command: str,
    max_context_chars: int = 8000,
) -> str:
    exit_code = state.last_test_exit_code if state.last_test_exit_code is not None else -1
    failure_summary = parse_test_output(
        output=state.last_test_output or "",
        exit_code=exit_code,
    )
    test_output = state.last_test_output or ""
    truncated_output, _ = truncate_output(test_output)
    file_hints = extract_file_hints(failure_summary)

    steps_taken = state.step_number
    max_steps = steps_taken + state.budget_remaining_steps
    time_remaining = state.budget_remaining_sec

    recent_actions = []
    for request, result in state.tool_history[-5:]:
        recent_actions.append(format_tool_result_summary(result))

    file_context_blocks = []
    seen_paths = set()
    remaining = max_context_chars
    for request, result in reversed(state.tool_history):
        if request.tool != ToolName.READ_FILE:
            continue
        path = request.params.get("path") if request.params else None
        if not path or path in seen_paths:
            continue
        if not result.data or "content" not in result.data:
            continue
        content = result.data.get("content", "")
        header = f"### {path}\n"
        available = remaining - len(header)
        if available <= 0:
            break
        truncated_content, _ = truncate_output(content, max_chars=available)
        block = f"{header}{truncated_content}"
        if len(block) > remaining:
            break
        file_context_blocks.append(block)
        remaining -= len(block)
        seen_paths.add(path)
        if remaining <= 0:
            break

    sections = [
        "## Task",
        task_description,
        "",
        "## Current Status",
        f"- Tests: {'PASSING' if exit_code == 0 else 'FAILING'} (exit code {exit_code})",
        f"- Steps taken: {steps_taken}/{max_steps}",
        f"- Time remaining: {time_remaining:.1f}s",
        f"- Test command: {test_command}",
        "",
        "## Test Failure Summary",
        "```",
        truncated_output,
        "```",
        "",
        "Failed tests:",
        "\n".join(failure_summary.failed_tests) if failure_summary.failed_tests else "None",
        "",
        "## Suggested Files to Investigate",
        "\n".join(file_hints) if file_hints else "None",
        "",
        "## Recent Actions",
        "\n".join(recent_actions) if recent_actions else "None",
    ]

    if file_context_blocks:
        sections.extend(
            [
                "",
                "## File Context",
                "\n".join(file_context_blocks),
            ]
        )

    sections.extend(
        [
            "",
            "## Available Tools",
            "- list_files: List files in directory",
            "- read_file: Read file contents",
            "- search: Search for patterns",
            "- apply_patch: Apply a unified diff patch",
            "- run: Run a command",
            "",
            "## Instructions",
            "Analyze the test failure and propose a fix. Use tools to investigate if needed, then apply a patch to fix the bug. After patching, run the tests to verify.",
        ]
    )

    return "\n".join(sections).strip()
