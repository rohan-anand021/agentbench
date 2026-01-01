import json
import logging
from agentbench.sandbox.docker_sandbox import DockerRunResult
from agentbench.sandbox.docker_sandbox import DockerSandbox
import subprocess
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from agentbench.sandbox.filesystem import (
    PathEscapeError,
    SymLinkError,
    resolve_safe_path,
    safe_glob,
)
from agentbench.tools.contract import (
    ListFilesParams,
    ReadFileParams,
    SearchParams,
    RunParams,
    ToolError,
    ToolName,
    ToolResult,
    ToolStatus,
)
from agentbench.util.process import check_exit_code
from agentbench.util.timeout import ToolTimeoutError, TOOL_TIMEOUTS
from agentbench.util.truncation import truncate_output

logger = logging.getLogger(__name__)


def list_files(
    request_id: str,
    workspace_root: Path,
    params: ListFilesParams
) -> ToolResult:
    """
    List files in a directory within the workspace.

    Returns files in deterministic sorted order.
    Filters out .git directory by default.
    """

    if params.glob is None:
        params.glob = '*'

    error = None
    data = None
    started_at = datetime.now()

    try:
        root_path = resolve_safe_path(
            workspace_root = workspace_root,
            relative_path = params.root
        )

        files = safe_glob(
            workspace_root = root_path,
            pattern = params.glob
        )

        logger.debug("list_files found %d files in %s", len(files), params.root)
        data = {"files": [str(f) for f in files]}

    except PathEscapeError as e:
        error = ToolError(
            error_type="path_escape",
            message=str(e),
            details={}
        )
    except SymLinkError as e:
        error = ToolError(
            error_type="symlink_blocked",
            message=str(e),
            details={}
        )
    except ToolTimeoutError as e:
        error = ToolError(
            error_type="timeout",
            message=str(e),
            details={"timeout_sec": TOOL_TIMEOUTS["list_files"]}
        )
    except Exception as e:
        logger.error("list_files failed: %s", e)
        error = ToolError(
            error_type=type(e).__name__,
            message=str(e),
            details={}
        )

    ended_at = datetime.now()

    return ToolResult(
        request_id=request_id,
        tool=ToolName.LIST_FILES,
        status=ToolStatus.SUCCESS if error is None else ToolStatus.ERROR,
        started_at=started_at,
        ended_at=ended_at,
        duration_sec=(ended_at - started_at).total_seconds(),
        data=data,
        error=error,
        exit_code=None,
        stdout_path=None,
        stderr_path=None
    )


def read_file(
    request_id: str,
    workspace_root: Path,
    params: ReadFileParams
) -> ToolResult:

    """
    Read file contents with optional line range.

    Line numbers are 1-indexed and inclusive.
    Truncates large files with clear metadata.
    """

    error = None
    data = None
    started_at = datetime.now()

    try:
        root_path = resolve_safe_path(
            workspace_root = workspace_root,
            relative_path = params.path
        )

        first_lines: list[str] = []
        last_buffer = deque(maxlen=5000)
        total_lines = 0

        with root_path.open('r', encoding = 'utf-8') as f:
            for i, line in enumerate(f, start=1):
                total_lines = i
                stripped = line.rstrip('\n')

                if i <= 5000:
                    first_lines.append(stripped)
                else:
                    last_buffer.append(stripped)

        if total_lines <= 10000:
            file_content = "\n".join(first_lines + list(last_buffer))
            truncated = False
        else:
            file_content = "\n".join(first_lines) + "\n\n... [truncated] ...\n\n" + "\n".join(last_buffer)
            truncated = True

        data = {
            "content": file_content,
            "truncated": truncated,
            "total_lines": total_lines,
            "start_line": 1,
            "end_line": total_lines if not truncated else None,
            "lines_included": None if not truncated else f"1-5000, {total_lines - 4999}-{total_lines}"
        }
        logger.debug("read_file read %d lines from %s, truncated=%s", total_lines, params.path, truncated)

    except FileNotFoundError as e:
        error = ToolError(
            error_type="file_not_found",
            message=f"File does not exist: {params.path}",
            details={"path": params.path}
        )
    except UnicodeDecodeError as e:
        error = ToolError(
            error_type="binary_file",
            message="Cannot read binary file",
            details={"path": params.path}
        )
    except PathEscapeError as e:
        error = ToolError(
            error_type="path_escape",
            message=str(e),
            details={"path": params.path}
        )
    except SymLinkError as e:
        error = ToolError(
            error_type="symlink_blocked",
            message=str(e),
            details={"path": params.path}
        )
    except ToolTimeoutError as e:
        error = ToolError(
            error_type="timeout",
            message=str(e),
            details={"timeout_sec": TOOL_TIMEOUTS["read_file"]}
        )
    except Exception as e:
        logger.error("read_file failed for %s: %s", params.path, e)
        error = ToolError(
            error_type=type(e).__name__,
            message=str(e),
            details={}
        )

    ended_at = datetime.now()

    return ToolResult(
        request_id=request_id,
        tool=ToolName.READ_FILE,
        status=ToolStatus.SUCCESS if error is None else ToolStatus.ERROR,
        started_at=started_at,
        ended_at=ended_at,
        duration_sec=(ended_at - started_at).total_seconds(),
        data=data,
        error=error,
        exit_code=None,
        stdout_path=None,
        stderr_path=None
    )


def search(
    request_id: str,
    workspace_root: Path,
    params: SearchParams
) -> ToolResult:
    """
    Search for text patterns across files.

    Uses ripgrep (rg) if available, falls back to Python.
    """

    error: ToolError | None = None
    timeout = TOOL_TIMEOUTS["search"]
    started_at = datetime.now()
    data: dict[str, Any] = {}
    logger.debug("Searching for '%s' with glob=%s", params.query, params.glob)

    cmd = ["rg",
            "--json",
            "--no-heading",
            "--ignore-case",]

    if not params.is_regex:
        cmd.append("--fixed-strings")
    cmd.extend([f"{params.query}",
                f"--context={params.context_lines}"])

    if params.glob:
        cmd.append(f"--glob={params.glob}")

    try:
        run = subprocess.run(
            args=cmd,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )

        if run.returncode != 0:
            if run.returncode == 1:
                # No matches found - not an error
                pass
            else:
                error = ToolError(
                    error_type="ripgrep_error",
                    message=f"ripgrep exited with code {run.returncode}",
                    details={"exit_code": run.returncode, "stderr": run.stderr}
                )

        match_count = 0
        matches: list[dict] = []
        context_buffer: list[str] = []
        current_match: dict | None = None

        for line in run.stdout.strip().splitlines():
            obj = json.loads(line)

            if obj["type"] == "context":
                context_line = obj["data"]["lines"]["text"].rstrip('\n')
                if current_match is None:
                    context_buffer.append(context_line)
                else:
                    if current_match["context_after"] is None:
                        current_match["context_after"] = []
                    current_match["context_after"].append(context_line)

            elif obj["type"] == "match":
                if current_match is not None:
                    matches.append(current_match)

                match_count += 1
                if match_count > params.max_results:
                    break

                current_match = {
                    "file": obj["data"]["path"]["text"],
                    "line": obj["data"]["line_number"],
                    "content": obj["data"]["lines"]["text"].rstrip('\n'),
                    "context_before": context_buffer.copy() if context_buffer else None,
                    "context_after": None
                }
                context_buffer.clear()

            elif obj["type"] == "begin":
                context_buffer.clear()

            elif obj["type"] == "end":
                if current_match is not None:
                    matches.append(current_match)
                    current_match = None
                context_buffer.clear()

        data["matches"] = matches
        data["truncated"] = match_count > params.max_results
        data["total_matches"] = min(match_count, params.max_results)
        logger.debug("Search found %d matches", data["total_matches"])

    except subprocess.TimeoutExpired as e:
        error = ToolError(
            error_type="timeout",
            message=f"Search timed out after {timeout} seconds",
            details={"timeout_sec": timeout}
        )
    except OSError as e:
        error = ToolError(
            error_type="ripgrep_unavailable",
            message=f"ripgrep not available: {str(e)}",
            details={}
        )
    except json.JSONDecodeError as e:
        error = ToolError(
            error_type="parse_error",
            message=f"Failed to parse ripgrep output: {str(e)}",
            details={}
        )
    except Exception as e:
        logger.error("Search failed: %s", e)
        error = ToolError(
            error_type=type(e).__name__,
            message=str(e),
            details={}
        )

    ended_at = datetime.now()

    return ToolResult(
        request_id=request_id,
        tool=ToolName.SEARCH,
        status=ToolStatus.SUCCESS if error is None else ToolStatus.ERROR,
        started_at=started_at,
        ended_at=ended_at,
        duration_sec=(ended_at - started_at).total_seconds(),
        data=data,
        error=error,
        exit_code=None,
        stdout_path=None,
        stderr_path=None
    )


def run_tool(
    workspace_root: Path,
    params: RunParams,
    sandbox: DockerSandbox,
    step_id: int,
    artifacts_dir: Path
) -> ToolResult:
    """
    Execute a command in the sandbox.
    
    Commands run inside Docker with network=none.
    Stdout/stderr are captured to artifacts.

    **Implementation details:**

    | Aspect | Behavior |
    |--------|----------|
    | Timeout | Use `params.timeout_sec` or default from task config |
    | Output files | Save to `logs/tool_step_NNNN_stdout.txt` and `_stderr.txt` |
    | Exit code | Capture and return in result |
    | Large output | Truncate to configurable limit (e.g., 100KB) |

    **Success data:**
    ```python
    {
        "exit_code": 0,
        "stdout_path": "logs/tool_step_0005_stdout.txt",
        "stderr_path": "logs/tool_step_0005_stderr.txt"
    }
    ```
    """

    started_at = datetime.now()
    error = None
    exit_code = None
    stdout_path = None
    stderr_path = None
    logger.debug("Executing command in sandbox: %s", params.command)

    try:
        exit_code, stdout_path, stderr_path = sandbox.run(
            workspace_host_path = workspace_root,
            command = params.command,
            network = "none",
            timeout_sec = params.timeout_sec if params.timeout_sec else 60,
            stdout_path = artifacts_dir / "logs" / f"tool_step_{step_id:04d}_stdout.txt",
            stderr_path = artifacts_dir / "logs" / f"tool_step_{step_id:04d}_stderr.txt",
        )

        if exit_code is not None:
            exit_error = check_exit_code("run", exit_code)
            if exit_error:
                error = ToolError(
                    error_type = "abnormal_exit",
                    message = str(exit_error),
                    details = {"exit_code": exit_code}
                )

    except TimeoutError as e:
        error = ToolError(
            error_type = "timeout",
            message = str(e)
        )
    except Exception as e:
        logger.error("Sandbox execution failed: %s", e)
        error = ToolError(
            error_type = "sandbox_error",
            message = str(e)
        )

    ended_at = datetime.now()
    logger.debug("Command completed with exit_code=%s in %.2fs", exit_code, (ended_at - started_at).total_seconds())

    data = None
    if not error and exit_code is not None:
        data = {
            "exit_code": exit_code,
            "stdout_path": str(stdout_path) if stdout_path else None,
            "stderr_path": str(stderr_path) if stderr_path else None,
        }

    return ToolResult(
        request_id = f"tool_step_{step_id:04d}",
        tool = ToolName.RUN,
        status = ToolStatus.SUCCESS if not error else ToolStatus.ERROR,
        started_at = started_at,
        ended_at = ended_at,
        duration_sec = (ended_at - started_at).total_seconds(),
        data = data,
        error = error,
        exit_code = exit_code,
        stdout_path = str(stdout_path) if stdout_path else None,
        stderr_path = str(stderr_path) if stderr_path else None,
    )


