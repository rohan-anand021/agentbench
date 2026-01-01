import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentbench.util.paths import ensure_dir

logger = logging.getLogger(__name__)


@dataclass
class DockerRunResult:
    exit_code: int
    stdout_path: Path
    stderr_path: Path


class DockerSandbox:
    def __init__(self, image: str, workdir: str = "/workspace"):
        self.image = image
        self.workdir = workdir

    def run(
        self,
        workspace_host_path,
        command,
        network,
        timeout_sec,
        stdout_path,
        stderr_path,
    ):
        # bash -lc - command
        # network - --network <network>

        if network not in ["none", "bridge"]:
            raise ValueError("Network must be 'none' or 'bridge'")

        ensure_dir(stdout_path.parent)
        ensure_dir(stderr_path.parent)

        workspace_host_path = Path(workspace_host_path).resolve()

        if not workspace_host_path.is_dir():
            raise ValueError("Workspace host path directory does not exist")

        cmd = [
            # fixed docker boilerplate
            "docker",
            "run",
            "--rm",
            # runtime configuration
            "--network",
            f"{network}",
            "-v",
            f"{workspace_host_path}:{self.workdir}",
            "-w",
            f"{self.workdir}",
            # image selection
            self.image,
            # command inside container
            "bash",
            "-lc",
            command,
        ]

        logger.debug(
            "Executing Docker command with network=%s, timeout=%ds",
            network,
            timeout_sec,
        )

        try:
            stdout = stdout_path.open("w", encoding="utf-8", newline="\n")
            stderr = stderr_path.open("w", encoding="utf-8", newline="\n")

        except PermissionError:
            raise

        else:
            try:
                with stdout, stderr:
                    run_result = subprocess.run(
                        args=cmd,
                        stdout=stdout,
                        stderr=stderr,
                        timeout=timeout_sec,
                    )

                exit_code = run_result.returncode

            except OSError as e:
                logger.error("I/O error during Docker command execution: %s", e)
                raise

            except subprocess.TimeoutExpired:
                logger.warning(
                    "Docker command timed out after %d seconds", timeout_sec
                )
                with stderr_path.open("a") as stderr:
                    stderr.write(
                        f"Execution timed out after {timeout_sec} seconds"
                    )

                exit_code = 124

        logger.debug("Docker command completed with exit code %d", exit_code)
        return DockerRunResult(exit_code, stdout_path, stderr_path)
