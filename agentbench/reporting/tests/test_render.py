from agentbench.reporting.models import (
    FailureBucket,
    HardestTaskRow,
    NormalizedAttempt,
    OverviewMetrics,
    ReportSummary,
    ReportWarning,
)
from agentbench.reporting.render import (
    default_output_paths,
    render_attempts_csv,
    render_markdown,
    render_summary_csv,
)


def make_summary() -> ReportSummary:
    ov = OverviewMetrics(
        total_attempts=3,
        passed=1,
        failed=2,
        pass_rate=1 / 3,
        duration_median=10.0,
        duration_p95=20.0,
    )
    failures = [
        FailureBucket(reason="tests_failed", count=1, percent=50.0),
        FailureBucket(reason="timeout", count=1, percent=50.0),
    ]
    hardest = [
        HardestTaskRow(
            task_id="b_task",
            failure_reason="timeout",
            attempts=1,
            passed=0,
            failed=1,
            avg_duration=20.0,
            artifact_path="tasks/b_task/",
        ),
        HardestTaskRow(
            task_id="a_task",
            failure_reason="tests_failed",
            attempts=2,
            passed=1,
            failed=1,
            avg_duration=10.0,
            artifact_path="tasks/a_task/",
        ),
    ]
    warnings = [
        ReportWarning(code="invalid_json", message="bad line", line_number=3, task_id=None)
    ]
    return ReportSummary(
        run_id="run1",
        suite="suite1",
        variant="v1",
        overview=ov,
        failure_histogram=failures,
        hardest_tasks=hardest,
        warnings=warnings,
    )


def test_markdown_contains_sections_and_tables():
    summary = make_summary()
    md = render_markdown(summary)
    assert "# AgentBench Report Summary" in md
    assert "## Overview" in md
    assert "| Total attempts | 3 |" in md
    assert "## Failure Histogram" in md
    assert "| tests_failed | 1 |" in md
    assert "## Hardest Tasks" in md
    assert "| b_task | 1 | 1 |" in md
    assert "## Warnings" in md
    assert "invalid_json" in md


def test_summary_csv_has_header_and_single_row():
    summary = make_summary()
    csv_txt = render_summary_csv(summary)
    rows = csv_txt.strip().splitlines()
    assert len(rows) == 2
    headers = rows[0].split(",")
    assert headers[:4] == ["run_id", "suite", "variant", "total_attempts"]


def test_attempts_csv_header_and_ordering():
    attempts = [
        NormalizedAttempt(
            task_id="b",
            suite=None,
            variant=None,
            passed=False,
            exit_code=1,
            failure_reason="x",
            duration_sec=1.0,
            steps_taken=None,
            artifact_paths={"task_dir": "/abs/path/b"},
            model_name=None,
        ),
        NormalizedAttempt(
            task_id="a",
            suite=None,
            variant=None,
            passed=True,
            exit_code=0,
            failure_reason=None,
            duration_sec=2.0,
            steps_taken=None,
            artifact_paths={"task_dir": "rel/a"},
            model_name=None,
        ),
    ]
    csv_txt = render_attempts_csv(attempts, run_id="r", suite="s", variant="v")
    rows = csv_txt.strip().splitlines()
    assert rows[0].split(",")[0:4] == ["run_id", "suite", "variant", "task_id"]
    assert rows[1].split(",")[3] == "a"
    assert rows[2].split(",")[3] == "b"
    assert rows[1].split(",")[11] == "rel/a"
    assert rows[2].split(",")[11] == "abs/path/b"


def test_default_output_paths_names(tmp_path):
    paths = default_output_paths(tmp_path)
    assert paths["markdown"].name == "report_summary.md"
    assert paths["summary_csv"].name == "report_summary.csv"
    assert paths["attempts_csv"].name == "report_attempts.csv"


def test_render_deterministic():
    summary = make_summary()
    md1 = render_markdown(summary)
    md2 = render_markdown(summary)
    assert md1 == md2
    csv1 = render_summary_csv(summary)
    csv2 = render_summary_csv(summary)
    assert csv1 == csv2
