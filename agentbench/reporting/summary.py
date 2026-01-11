import math
from collections import Counter, defaultdict
from statistics import median
from typing import Iterable

from agentbench.reporting.models import (
    FailureBucket,
    HardestTaskRow,
    NormalizedAttempt,
    OverviewMetrics,
    ReportSummary,
)


def compute_summary(attempts: list[NormalizedAttempt]) -> ReportSummary:
    overview = compute_overview(attempts)
    failures = compute_failure_histogram(attempts)
    hardest = compute_hardest_tasks(attempts)

    suites = sorted({a.suite for a in attempts if a.suite})
    variants = sorted({a.variant for a in attempts if a.variant})

    return ReportSummary(
        run_id=None,
        suite=suites[0] if len(suites) == 1 else None,
        variant=variants[0] if len(variants) == 1 else None,
        overview=overview,
        failure_histogram=failures,
        hardest_tasks=hardest,
        warnings=[],
    )


def compute_overview(attempts: list[NormalizedAttempt]) -> OverviewMetrics:
    total = len(attempts)
    passed = sum(1 for a in attempts if a.passed)
    failed = total - passed
    pass_rate = (passed / total) if total else 0.0

    durations = [a.duration_sec for a in attempts if a.duration_sec is not None]
    durations_sorted = sorted(durations)

    duration_median = median(durations_sorted) if durations_sorted else None
    duration_p95 = _percentile(durations_sorted, 95) if durations_sorted else None

    return OverviewMetrics(
        total_attempts=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        duration_median=duration_median,
        duration_p95=duration_p95,
    )


def compute_failure_histogram(
    attempts: list[NormalizedAttempt],
) -> list[FailureBucket]:
    failed = [a for a in attempts if not a.passed]
    if not failed:
        return []

    counts: Counter[str] = Counter()
    for attempt in failed:
        reason = attempt.failure_reason or "unknown"
        counts[reason] += 1

    total_failed = sum(counts.values())
    buckets: list[FailureBucket] = []
    for reason, count in counts.items():
        percent = (count / total_failed) * 100 if total_failed else 0.0
        buckets.append(
            FailureBucket(
                reason=reason,
                count=count,
                percent=percent,
            )
        )

    buckets.sort(key=lambda b: (-b.count, b.reason))
    return buckets


def compute_hardest_tasks(
    attempts: list[NormalizedAttempt],
    limit: int = 10,
) -> list[HardestTaskRow]:
    grouped: dict[str, list[NormalizedAttempt]] = defaultdict(list)
    for attempt in attempts:
        grouped[attempt.task_id].append(attempt)

    rows: list[HardestTaskRow] = []
    for task_id, task_attempts in grouped.items():
        total = len(task_attempts)
        passed = sum(1 for a in task_attempts if a.passed)
        failed = total - passed
        if total == 0:
            continue
        failure_rate = failed / total

        durations = [a.duration_sec for a in task_attempts if a.duration_sec is not None]
        avg_duration = sum(durations) / len(durations) if durations else None

        failure_reasons = [
            a.failure_reason or "unknown" for a in task_attempts if not a.passed
        ]
        failure_reason = None
        if failure_reasons:
            freq = Counter(failure_reasons)
            top_count = max(freq.values())
            candidates = [r for r, c in freq.items() if c == top_count]
            failure_reason = sorted(candidates)[0]

        artifact_path = None
        for a in task_attempts:
            if a.artifact_paths:
                artifact_path = a.artifact_paths.get("task_dir")
                if artifact_path:
                    break

        rows.append(
            HardestTaskRow(
                task_id=task_id,
                failure_reason=failure_reason,
                attempts=total,
                passed=passed,
                failed=failed,
                avg_duration=avg_duration,
                artifact_path=artifact_path,
            )
        )

    rows.sort(
        key=lambda r: (
            -(r.failed / r.attempts if r.attempts else 0),
            -(r.avg_duration or 0.0),
            r.task_id,
        )
    )
    return rows[:limit]


def _percentile(values: Iterable[float], q: int) -> float | None:
    vals = list(values)
    if not vals:
        return None
    vals.sort()
    n = len(vals)
    rank = math.ceil(q / 100 * n) - 1
    rank = max(0, min(rank, n - 1))
    return vals[rank]
