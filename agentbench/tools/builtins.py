from pathlib import Path
from datetime import datetime
from collections import deque
import subprocess
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
    data = None
    started_at = datetime.now()
    params.glob = params.glob if params.glob else "*"

    search_cmd = ["rg", 
                  "--json", 
                  f"--max-count={params.max_results}", 
                  "--no-heading",
                  f"{params.query}",
                  f"{params.glob}"]

    try:
        search_run = subprocess.run(
            args = search_cmd,
            capture_output = True,
            text = True,
            timeout = 60,
            check = False
        )

        

        data = {

        }
    
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






    

    


