from pathlib import Path
import json

import pytest

from agentbench.reporting.inputs import (
    load_run_dir,
    normalize_attempt,
    read_attempts_jsonl,
)
from agentbench.reporting.models import NormalizedAttempt


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_normalize_failure_reason_lowercase():
    raw = {
        "task_id": "t1",
        "result": {"passed": True, "failure_reason": "TESTS_FAILED"},
    }
    normalized = normalize_attempt(raw)
    assert isinstance(normalized, NormalizedAttempt)
    assert normalized.failure_reason == "tests_failed"


def test_normalize_missing_task_id_skipped():
    raw = {"result": {"passed": True}}
    assert normalize_attempt(raw) is None


def test_read_attempts_invalid_json(tmp_path: Path):
    attempts_path = tmp_path / "attempts.jsonl"
    with attempts_path.open("w", encoding="utf-8") as f:
        f.write('{"task_id": "t1"}\n')
        f.write("{invalid json}\n")
    raw_attempts, warnings, invalid = read_attempts_jsonl(attempts_path)
    assert len(raw_attempts) == 1
    assert invalid == 1
    assert any(w.code == "invalid_json" for w in warnings)


def test_load_run_dir_success(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"run_id": "r1", "suite": "s1", "variant": "v1"}),
        encoding="utf-8",
    )
    write_jsonl(
        run_dir / "attempts.jsonl",
        [
            {
                "task_id": "t1",
                "suite": "s1",
                "variant": "v1",
                "result": {"passed": True, "exit_code": 0},
                "duration_sec": 1.5,
            }
        ],
    )
    inputs = load_run_dir(run_dir)
    assert inputs.run_metadata.run_id == "r1"
    assert len(inputs.attempts) == 1
    assert inputs.attempts[0].task_id == "t1"
    assert inputs.warnings == []
    assert inputs.invalid_lines == 0


def test_load_run_dir_missing_run_json_warns(tmp_path: Path):
    run_dir = tmp_path / "run2"
    run_dir.mkdir()
    write_jsonl(
        run_dir / "attempts.jsonl",
        [{"task_id": "t1", "result": {"passed": False}}],
    )
    inputs = load_run_dir(run_dir)
    assert inputs.run_metadata.run_id == "run2"
    assert any(w.code == "missing_run_json" for w in inputs.warnings)


def test_missing_task_id_adds_warning(tmp_path: Path):
    run_dir = tmp_path / "run_missing_task"
    run_dir.mkdir()
    write_jsonl(run_dir / "attempts.jsonl", [{}])
    inputs = load_run_dir(run_dir)
    assert len(inputs.attempts) == 0
    assert any(w.code == "missing_field" for w in inputs.warnings)


def test_missing_attempts_jsonl_raises(tmp_path: Path):
    run_dir = tmp_path / "run3"
    run_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        load_run_dir(run_dir)
