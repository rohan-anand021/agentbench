from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_serializer

from agentbench.scoring import FailureReason


class RepoSpec(BaseModel):
    model_config = ConfigDict(
        ser_json_timedelta="float",
    )

    url: str
    commit: str


class EnvironmentSpec(BaseModel):
    docker_image: str
    workdir: str
    timeout_sec: int


class SetupSpec(BaseModel):
    commands: list[str]


class RunSpec(BaseModel):
    command: str

class AgentSpec(BaseModel):
    entrypoint: str
    max_steps: int


class TaskSpec(BaseModel):
    model_config = ConfigDict(
        ser_json_timedelta="float",
    )

    id: str
    suite: str
    repo: RepoSpec
    environment: EnvironmentSpec
    setup: SetupSpec
    run: RunSpec
    source_path: Path
    agent: AgentSpec | None = None

    @field_serializer("source_path")
    def serialize_path(self, v: Path) -> str:
        return str(v)


# ---


class ValidationResult(BaseModel):
    """
    Define `ValidationResult` dataclass:
    - `task_id: str`
    - `valid: bool` (True if baseline fails as expected)
    - `exit_code: int`
    - `stdout_path: Path`
    - `stderr_path: Path`
    - `error_reason: str | None` (e.g., "baseline_passed", "setup_failed", "timeout")
    - `duration_sec: float`
    """

    model_config = ConfigDict(
        ser_json_timedelta="float",
    )

    task_id: str
    valid: bool
    exit_code: int
    stdout_path: Path | None
    stderr_path: Path | None
    error_reason: FailureReason | None
    duration_sec: float

    @field_serializer("stdout_path", "stderr_path")
    def serialize_paths(self, v: Path) -> str:
        return str(v)
