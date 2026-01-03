from dataclasses import dataclass
from pathlib import Path

@dataclass
class DockerRunResult:
    exit_code: int
    stdout_path: Path
    stderr_path: Path
    docker_cmd: list[str]
