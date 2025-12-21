from pathlib import Path
from datetime import datetime
from collections import deque
import subprocess
import json
from typing import Any

from agentbench.tools.contract import (
    ListFilesParams, 
    ReadFileParams,
    ToolResult, 
    ToolName, 
    ToolError, 
    ToolStatus,
    SearchParams
)
from agentbench.sandbox.filesystem import safe_glob, resolve_safe_path
from agentbench.util.process import check_exit_code

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

        data = {"files": [str(f) for f in files]}
    
    except Exception as e:
        error = e
    
    finally:
        ended_at = datetime.now()

        return ToolResult(
            request_id = request_id,
            tool = ToolName.LIST_FILES,
            status = ToolStatus.SUCCESS if not error else ToolStatus.ERROR,
            started_at = started_at,
            ended_at = ended_at,
            duration_sec = (ended_at - started_at).total_seconds(),
            data = data,
            error = ToolError(
                error_type = type(error).__name__,
                message = str(error),
                details = {f"Error {type(error).__name__}": f"{str(error)}"}
            ) if error else None,
            exit_code = None,
            stdout_path = None,
            stderr_path = None
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
        
    except FileNotFoundError as e:
        error = e

    except UnicodeDecodeError as e:
        error = e
    
    finally:
        ended_at = datetime.now()

        error_obj = None
        if error is not None:
            if isinstance(error, UnicodeDecodeError):
                error_obj = ToolError(
                    error_type = "binary_file",
                    message = "Cannot read binary file",
                    details = {}
                )
            else:
                error_obj = ToolError(
                    error_type = type(error).__name__,
                    message = str(error),
                    details = {}
                )

        return ToolResult(
            request_id = request_id,
            tool = ToolName.READ_FILE,
            status = ToolStatus.SUCCESS if not error else ToolStatus.ERROR,
            started_at = started_at,
            ended_at = ended_at,
            duration_sec = (ended_at - started_at).total_seconds(),
            data = data,
            error = error_obj,
            exit_code = None,
            stdout_path = None,
            stderr_path = None
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

    error = None
    timeout = 60
    started_at = datetime.now()
    data: dict[str, Any] = {}

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
            args = cmd,
            cwd = workspace_root,
            capture_output = True,
            text = True,
            timeout = 60,
            check = False
        )

        if run.returncode != 0:
            if run.returncode == 1:
                pass
            else:
                error = check_exit_code("search", run.returncode)
        
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
                    

    except subprocess.TimeoutExpired as e:
        error = e
    except OSError as e:
        error = e

    finally:
        ended_at = datetime.now()

        error_obj = None
        if error is not None:
            if isinstance(error, subprocess.TimeoutExpired):
                error_obj = ToolError(
                    error_type = "timeout",
                    message = f"Operation timed out after {timeout} seconds",
                    details = {}
                )
            elif isinstance(error, OSError):
                error_obj = ToolError(
                    error_type = "docker",
                    message = f"Docker unavailable: {str(error)}",
                    details = {}
                )
            else:
                error_obj = ToolError(
                    error_type = type(error).__name__,
                    message = str(error),
                    details = {}
                )

        return ToolResult(
            request_id = request_id,
            tool = ToolName.SEARCH,
            status = ToolStatus.SUCCESS if not error else ToolStatus.ERROR,
            started_at = started_at,
            ended_at = ended_at,
            duration_sec = (ended_at - started_at).total_seconds(),
            data = data,
            error = error_obj,
            exit_code = None,
            stdout_path = None,
            stderr_path = None
        )




