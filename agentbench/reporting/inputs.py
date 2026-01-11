from pathlib import Path
from typing import Any

from agentbench.reporting.models import (
    NormalizedAttempt,
    ReportInputs,
    ReportWarning,
    RunMetadata,
)

REQUIRED_FILES = ("run.json", "attempts.jsonl")
OPTIONAL_FILES = (
    "events.jsonl",
    "report_summary.md",
    "report_summary.csv",
    "report_attempts.csv",
)


def expected_paths(run_dir: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name in REQUIRED_FILES + OPTIONAL_FILES:
        paths[name] = run_dir / name
    return paths


def load_run_dir(run_dir: Path) -> ReportInputs:
    run_dir = Path(run_dir)
    paths = expected_paths(run_dir)

    warnings: list[ReportWarning] = []

    try:
        raw_run = read_run_metadata(paths["run.json"])
    except FileNotFoundError:
        raw_run = {}
        warnings.append(
            ReportWarning(
                code="missing_run_json",
                message="run.json not found",
                line_number=None,
                task_id=None,
            )
        )

    if not paths["attempts.jsonl"].exists():
        raise FileNotFoundError(f"attempts.jsonl not found in {run_dir}")

    raw_attempts, attempt_warnings, invalid_lines = read_attempts_jsonl(
        paths["attempts.jsonl"]
    )
    warnings.extend(attempt_warnings)

    attempts: list[NormalizedAttempt] = []
    for raw in raw_attempts:
        if not raw.get("task_id"):
            warnings.append(
                ReportWarning(
                    code="missing_field",
                    message="task_id is required",
                    line_number=None,
                    task_id=None,
                )
            )
            continue
        normalized = normalize_attempt(raw)
        if normalized is None:
            warnings.append(
                ReportWarning(
                    code="invalid_record",
                    message="record could not be normalized",
                    line_number=None,
                    task_id=raw.get("task_id"),
                )
            )
            continue
        attempts.append(normalized)

    run_metadata = RunMetadata(
        run_id=str(raw_run.get("run_id") or run_dir.name),
        suite=raw_run.get("suite"),
        variant=raw_run.get("variant"),
        started_at=raw_run.get("started_at"),
        ended_at=raw_run.get("ended_at"),
        task_count=raw_run.get("task_count"),
    )

    return ReportInputs(
        run_dir=run_dir,
        run_metadata=run_metadata,
        attempts=attempts,
        warnings=warnings,
        invalid_lines=invalid_lines,
    )


def read_run_metadata(run_json_path: Path) -> dict[str, Any]:
    run_json_path = Path(run_json_path)
    if not run_json_path.exists():
        raise FileNotFoundError(run_json_path)
    import json

    with run_json_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_attempts_jsonl(
    attempts_path: Path,
) -> tuple[list[dict[str, Any]], list[ReportWarning], int]:
    attempts_path = Path(attempts_path)
    import json

    raw_attempts: list[dict[str, Any]] = []
    warnings: list[ReportWarning] = []
    invalid_lines = 0

    with attempts_path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw_attempts.append(json.loads(line))
            except json.JSONDecodeError as exc:
                invalid_lines += 1
                warnings.append(
                    ReportWarning(
                        code="invalid_json",
                        message=str(exc),
                        line_number=idx,
                        task_id=None,
                    )
                )

    return raw_attempts, warnings, invalid_lines


def normalize_attempt(raw: dict[str, Any]) -> NormalizedAttempt | None:
    task_id = raw.get("task_id")
    if not task_id:
        return None

    result = raw.get("result") or {}
    model = raw.get("model") or {}

    passed = bool(result.get("passed")) if "passed" in result else False
    failure_reason = result.get("failure_reason")
    if isinstance(failure_reason, str):
        failure_reason = failure_reason.lower()
    elif failure_reason is not None:
        failure_reason = str(failure_reason).lower()

    return NormalizedAttempt(
        task_id=task_id,
        suite=raw.get("suite"),
        variant=raw.get("variant"),
        passed=passed,
        exit_code=result.get("exit_code"),
        failure_reason=failure_reason,
        duration_sec=raw.get("duration_sec"),
        steps_taken=result.get("steps_taken"),
        artifact_paths=raw.get("artifact_paths") or {},
        model_name=model.get("name"),
    )
