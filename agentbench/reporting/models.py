from pathlib import Path

from pydantic import BaseModel, Field


class ReportWarning(BaseModel):
    code: str
    message: str
    line_number: int | None = None
    task_id: str | None = None


class RunMetadata(BaseModel):
    run_id: str
    suite: str | None = None
    variant: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    task_count: int | None = None


class NormalizedAttempt(BaseModel):
    task_id: str
    suite: str | None = None
    variant: str | None = None
    passed: bool
    exit_code: int | None = None
    failure_reason: str | None = None
    duration_sec: float | None = None
    steps_taken: int | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    model_name: str | None = None


class ReportInputs(BaseModel):
    run_dir: Path
    run_metadata: RunMetadata
    attempts: list[NormalizedAttempt]
    warnings: list[ReportWarning]
    invalid_lines: int = 0


class OverviewMetrics(BaseModel):
    total_attempts: int
    passed: int
    failed: int
    pass_rate: float
    duration_median: float | None = None
    duration_p95: float | None = None


class FailureBucket(BaseModel):
    reason: str
    count: int
    percent: float


class HardestTaskRow(BaseModel):
    task_id: str
    failure_reason: str | None
    attempts: int
    passed: int
    failed: int
    avg_duration: float | None
    artifact_path: str | None


class ReportSummary(BaseModel):
    run_id: str | None
    suite: str | None
    variant: str | None
    overview: OverviewMetrics
    failure_histogram: list[FailureBucket] = Field(default_factory=list)
    hardest_tasks: list[HardestTaskRow] = Field(default_factory=list)
    warnings: list[ReportWarning] = Field(default_factory=list)
