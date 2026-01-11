from __future__ import annotations

import csv
import io
from pathlib import Path

from agentbench.reporting.models import NormalizedAttempt, ReportSummary
from agentbench.reporting.templates import (
    FAILURE_HEADER,
    HARDEST_HEADER,
    OVERVIEW_HEADER,
    WARNINGS_HEADER,
)


def render_markdown(summary: ReportSummary) -> str:
    lines: list[str] = []
    header_parts = []
    if summary.run_id:
        header_parts.append(f"Run: {summary.run_id}")
    if summary.suite:
        header_parts.append(f"Suite: {summary.suite}")
    if summary.variant:
        header_parts.append(f"Variant: {summary.variant}")
    header_line = " | ".join(header_parts) if header_parts else "AgentBench Report Summary"

    lines.append("# AgentBench Report Summary")
    lines.append("")
    lines.append(header_line)
    lines.append("")

    ov = summary.overview
    lines.append(OVERVIEW_HEADER)
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total attempts | {ov.total_attempts} |")
    lines.append(f"| Passed | {ov.passed} |")
    lines.append(f"| Failed | {ov.failed} |")
    lines.append(f"| Pass rate | {format_percent(ov.pass_rate)} |")
    lines.append(f"| Median duration | {format_duration(ov.duration_median)} |")
    lines.append(f"| P95 duration | {format_duration(ov.duration_p95)} |")
    lines.append("")

    lines.append(FAILURE_HEADER)
    lines.append("")
    lines.append("| Failure Reason | Count | Percent |")
    lines.append("|----------------|-------|---------|")
    if summary.failure_histogram:
        for bucket in summary.failure_histogram:
            lines.append(
                f"| {bucket.reason} | {bucket.count} | {format_percent(bucket.percent / 100, decimals=1)} |"
            )
    else:
        lines.append("| (none) | 0 | 0.0% |")
    lines.append("")

    lines.append(HARDEST_HEADER)
    lines.append("")
    lines.append("| Task ID | Attempts | Failed | Avg Duration | Failure Reason | Artifact |")
    lines.append("|---------|----------|--------|--------------|----------------|----------|")
    if summary.hardest_tasks:
        for row in summary.hardest_tasks:
            lines.append(
                "| {task_id} | {attempts} | {failed} | {avg_duration} | {failure_reason} | {artifact} |".format(
                    task_id=row.task_id,
                    attempts=row.attempts,
                    failed=row.failed,
                    avg_duration=format_duration(row.avg_duration),
                    failure_reason=row.failure_reason or "",
                    artifact=row.artifact_path or "",
                )
            )
    else:
        lines.append("| (none) | 0 | 0 | 0.0s |  |  |")
    lines.append("")

    lines.append(WARNINGS_HEADER)
    lines.append("")
    if summary.warnings:
        for warn in summary.warnings:
            parts = [warn.code, warn.message]
            if warn.task_id:
                parts.append(f"task={warn.task_id}")
            if warn.line_number is not None:
                parts.append(f"line={warn.line_number}")
            lines.append(f"- {' | '.join(parts)}")
    else:
        lines.append("None")

    return "\n".join(lines)


def render_summary_csv(summary: ReportSummary) -> str:
    headers = [
        "run_id",
        "suite",
        "variant",
        "total_attempts",
        "passed",
        "failed",
        "pass_rate",
        "duration_median",
        "duration_p95",
        "warning_count",
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    ov = summary.overview
    writer.writerow(
        [
            summary.run_id or "",
            summary.suite or "",
            summary.variant or "",
            ov.total_attempts,
            ov.passed,
            ov.failed,
            f"{ov.pass_rate:.6f}",
            format_number(ov.duration_median),
            format_number(ov.duration_p95),
            len(summary.warnings),
        ]
    )
    return output.getvalue()


def render_attempts_csv(
    attempts: list[NormalizedAttempt],
    run_id: str | None,
    suite: str | None,
    variant: str | None,
) -> str:
    headers = [
        "run_id",
        "suite",
        "variant",
        "task_id",
        "passed",
        "failure_reason",
        "exit_code",
        "duration_sec",
        "steps_taken",
        "stop_reason",
        "model_name",
        "artifact_task_dir",
        "failing_stdout",
        "passing_stdout",
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    attempts_sorted = sorted(attempts, key=lambda a: a.task_id)
    for attempt in attempts_sorted:
        paths = attempt.artifact_paths or {}
        # Normalize artifact paths to be relative-safe strings
        task_dir = _safe_relpath(paths.get("task_dir"))
        failing_stdout = _safe_relpath(paths.get("failing_stdout"))
        passing_stdout = _safe_relpath(paths.get("passing_stdout"))
        writer.writerow(
            [
                run_id or "",
                suite or attempt.suite or "",
                variant or attempt.variant or "",
                attempt.task_id,
                str(bool(attempt.passed)).lower(),
                attempt.failure_reason or "",
                attempt.exit_code if attempt.exit_code is not None else "",
                format_number(attempt.duration_sec),
                attempt.steps_taken if attempt.steps_taken is not None else "",
                "",
                attempt.model_name or "",
                task_dir or "",
                failing_stdout or "",
                passing_stdout or "",
            ]
        )
    return output.getvalue()


def default_output_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "markdown": run_dir / "report_summary.md",
        "summary_csv": run_dir / "report_summary.csv",
        "attempts_csv": run_dir / "report_attempts.csv",
    }


def format_percent(value: float, decimals: int = 1) -> str:
    pct = value * 100
    return f"{pct:.{decimals}f}%"


def format_duration(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}s"


def format_number(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _safe_relpath(value: str | None) -> str | None:
    if not value:
        return None
    # Avoid absolute paths; keep as provided if relative
    if value.startswith(("/", "\\")):
        return value.lstrip("/\\")
    return value
