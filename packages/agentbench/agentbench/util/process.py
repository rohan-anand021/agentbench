import logging
import subprocess
from pathlib import Path

from agentbench.util.paths import ensure_dir

logger = logging.getLogger(__name__)


def run_command(
    cmd_name: str,
    cmd: list[str],
    timeout: int,
    logs_dir: Path,
    cwd: Path | None = None,
):
    stdout_path = Path(logs_dir, f"{cmd_name}_stdout.txt")
    stderr_path = Path(logs_dir, f"{cmd_name}_stderr.txt")
    exit_code = None

    logs_dir = ensure_dir(logs_dir)

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
                    cwd=cwd,
                    stdout=stdout,
                    stderr=stderr,
                    timeout=timeout,
                )

                exit_code = run_result.returncode

        except OSError as e:
            logger.error("I/O error during command execution: %s", e)
            raise

        except subprocess.TimeoutExpired:
            with stderr_path.open("a") as stderr:
                stderr.write(f"Execution timed out after {timeout} seconds")

            exit_code = 124

    return stdout_path, stderr_path, exit_code


def check_exit_code(
    cmd_name: str, exit_code: int, success: int = 0
) -> Exception | None:
    if exit_code != success:
        logger.error("%s failed with exit code %d", cmd_name, exit_code)
        return ValueError(f"Operation {cmd_name} failed")
