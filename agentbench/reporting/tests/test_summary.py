from agentbench.reporting.models import NormalizedAttempt
from agentbench.reporting.summary import (
    compute_failure_histogram,
    compute_hardest_tasks,
    compute_overview,
    compute_summary,
)


def make_attempt(**kwargs) -> NormalizedAttempt:
    defaults = {
        "task_id": "t1",
        "suite": "s1",
        "variant": "v1",
        "passed": False,
        "exit_code": 1,
        "failure_reason": "tests_failed",
        "duration_sec": 10.0,
        "steps_taken": None,
        "artifact_paths": {},
        "model_name": None,
    }
    defaults.update(kwargs)
    return NormalizedAttempt(**defaults)


def test_compute_overview_counts_and_rate():
    attempts = [
        make_attempt(task_id="a", passed=True, duration_sec=5.0),
        make_attempt(task_id="b", passed=False, duration_sec=15.0),
    ]
    ov = compute_overview(attempts)
    assert ov.total_attempts == 2
    assert ov.passed == 1
    assert ov.failed == 1
    assert abs(ov.pass_rate - 0.5) < 1e-9
    assert ov.duration_median == 10.0
    assert ov.duration_p95 == 15.0


def test_compute_failure_histogram_sorted():
    attempts = [
        make_attempt(task_id="a", passed=False, failure_reason="timeout"),
        make_attempt(task_id="b", passed=False, failure_reason="tests_failed"),
        make_attempt(task_id="c", passed=False, failure_reason="tests_failed"),
    ]
    buckets = compute_failure_histogram(attempts)
    assert [b.reason for b in buckets] == ["tests_failed", "timeout"]
    assert [b.count for b in buckets] == [2, 1]


def test_compute_hardest_tasks_ordering():
    attempts = [
        make_attempt(task_id="a", passed=False, duration_sec=20.0),
        make_attempt(task_id="a", passed=True, duration_sec=5.0),
        make_attempt(task_id="b", passed=False, duration_sec=15.0),
        make_attempt(task_id="b", passed=False, duration_sec=10.0),
    ]
    rows = compute_hardest_tasks(attempts)
    assert [r.task_id for r in rows] == ["b", "a"]
    assert rows[0].failed == 2
    assert rows[1].failed == 1


def test_compute_summary_suite_variant_singleton():
    attempts = [
        make_attempt(task_id="a", suite="s1", variant="v1"),
        make_attempt(task_id="b", suite="s1", variant="v1"),
    ]
    summary = compute_summary(attempts)
    assert summary.suite == "s1"
    assert summary.variant == "v1"


def test_compute_summary_mixed_suite_variant_none():
    attempts = [
        make_attempt(task_id="a", suite="s1", variant="v1"),
        make_attempt(task_id="b", suite="s2", variant="v2"),
    ]
    summary = compute_summary(attempts)
    assert summary.suite is None
    assert summary.variant is None


def test_failure_histogram_tiebreak_reason_sort():
    attempts = [
        make_attempt(task_id="a", passed=False, failure_reason="b_reason"),
        make_attempt(task_id="b", passed=False, failure_reason="a_reason"),
    ]
    buckets = compute_failure_histogram(attempts)
    assert [b.reason for b in buckets] == ["a_reason", "b_reason"]
