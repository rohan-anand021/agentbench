from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class ToolName(StrEnum):
    LIST_FILES = "list_files"
    READ_FILE = "read_file"
    SEARCH = "search"
    APPLY_PATCH = "apply_patch"
    RUN = "run"

class ToolRequest(BaseModel):
    tool: ToolName
    params: dict[str, Any]
    request_id: str

class ListFilesParams(BaseModel):
    root: str = '.'
    glob: str | None = None

class ReadFileParams(BaseModel):
    path: str
    start_line: int | None = None
    end_line: int | None = None

class SearchParams(BaseModel):
    query: str
    glob: str | None = None
    max_results: int = 50
    context_lines: int = 2
    is_regex: bool = False

class ApplyPatchParams(BaseModel):
    unified_diff: str

class RunParams(BaseModel):
    command: str
    timeout_sec: int | None = None
    env: dict[str, str] | None = None

class ToolStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"

class ToolError(BaseModel):
    error_type: str
    message: str
    details: dict[str, Any] | None = None

class ToolResult(BaseModel):
    request_id: str
    tool: ToolName
    status: ToolStatus
    started_at: datetime
    ended_at: datetime
    duration_sec: float
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    exit_code: int | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None

class SearchMatch(BaseModel):
    file: str
    line: int
    content: str
    context_before: list[str] | None = None
    context_after: list[str] | None = None




