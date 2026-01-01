# Tool API Documentation

This document describes the stable tool API contract for AgentBench. All agents interact with the workspace through these five tools.

## Overview

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `list_files` | List files in workspace | `root`, `glob` |
| `read_file` | Read file contents | `path`, `start_line`, `end_line` |
| `search` | Search for text patterns | `query`, `glob`, `max_results` |
| `apply_patch` | Apply unified diff | `unified_diff` |
| `run` | Execute command | `command`, `timeout_sec`, `env` |

## Data Types

### ToolRequest

Every tool call is represented as a `ToolRequest`:

```python
class ToolRequest(BaseModel):
    tool: ToolName          # Which tool to call
    params: dict[str, Any]  # Tool-specific parameters
    request_id: str         # Unique ID for correlation
```

### ToolResult

Every tool returns a structured `ToolResult`:

```python
class ToolResult(BaseModel):
    request_id: str         # Correlates with ToolRequest
    tool: ToolName          # Which tool was called
    status: ToolStatus      # "success" or "error"
    started_at: datetime    # When execution began
    ended_at: datetime      # When execution completed
    duration_sec: float     # Wall-clock time
    data: dict | None       # Tool-specific result data
    error: ToolError | None # Structured error (if failed)
    exit_code: int | None   # For run tool only
    stdout_path: str | None # For run tool only
    stderr_path: str | None # For run tool only
```

### ToolError

All failures include structured error information:

```python
class ToolError(BaseModel):
    error_type: str         # e.g., "path_escape", "timeout"
    message: str            # Human-readable description
    details: dict | None    # Additional context
```

## Tools

### list_files

**Purpose**: List files in a directory within the workspace.

**Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `root` | `str` | `"."` | Directory to list (relative to workspace) |
| `glob` | `str \| None` | `None` | Glob pattern to filter files |

**Returns**: Sorted list of file paths (relative to `root`).

**Example**:
```python
ListFilesParams(root="src", glob="**/*.py")
# Returns: {"files": ["main.py", "utils.py", "deep/nested/module.py"]}
```

**Behavior**:
- Files are always sorted alphabetically (deterministic)
- `.git/` directory is excluded by default
- Symlinks are excluded
- Maximum 1000 files returned

**Error Types**:
- `path_escape`: Path would escape workspace
- `symlink_blocked`: Path contains symlink
- `timeout`: Operation timed out (30s limit)

---

### read_file

**Purpose**: Read file contents with optional line range.

**Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | (required) | File path relative to workspace |
| `start_line` | `int \| None` | `None` | Start line (1-indexed, inclusive) |
| `end_line` | `int \| None` | `None` | End line (1-indexed, inclusive) |

**Returns**: File content with metadata.

**Example**:
```python
ReadFileParams(path="src/main.py")
# Returns: {
#     "content": "def main():\n    ...",
#     "truncated": False,
#     "total_lines": 42,
#     "start_line": 1,
#     "end_line": 42
# }
```

**Behavior**:
- Line numbers are 1-indexed
- Large files (>10,000 lines) are truncated to first 5,000 + last 5,000 lines
- Truncation metadata is included in response

**Error Types**:
- `file_not_found`: File does not exist
- `binary_file`: File contains non-UTF-8 content
- `path_escape`: Path would escape workspace
- `timeout`: Operation timed out (10s limit)

---

### search

**Purpose**: Search for text patterns across files.

**Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | (required) | Text or regex pattern |
| `glob` | `str \| None` | `None` | File pattern to search in |
| `max_results` | `int` | `50` | Maximum matches to return |
| `context_lines` | `int` | `2` | Lines of context (0-10) |
| `is_regex` | `bool` | `False` | Treat query as regex |

**Returns**: List of matches with context.

**Example**:
```python
SearchParams(query="def main", glob="**/*.py", max_results=10)
# Returns: {
#     "matches": [
#         {
#             "file": "src/main.py",
#             "line": 5,
#             "content": "def main():",
#             "context_before": ["", "# Entry point"],
#             "context_after": ["    print('hello')"]
#         }
#     ],
#     "truncated": False,
#     "total_matches": 1
# }
```

**Behavior**:
- Uses ripgrep (`rg`) for fast searching
- Case-insensitive by default
- Results ordered by file path, then line number
- Binary files are skipped

**Error Types**:
- `timeout`: Search timed out (60s limit)
- `ripgrep_unavailable`: ripgrep not installed
- `ripgrep_error`: ripgrep returned non-zero exit code

---

### apply_patch

**Purpose**: Apply a unified diff patch to files.

**Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `unified_diff` | `str` | (required) | Standard unified diff format |

**Returns**: List of changed files.

**Example**:
```python
ApplyPatchParams(unified_diff='''--- a/src/main.py
+++ b/src/main.py
@@ -1,4 +1,4 @@
 def add(a, b):
-    return a - b
+    return a + b
''')
# Returns: {"changed_files": ["src/main.py"], "patch_size_bytes": 89}
```

**Behavior**:
- Uses the `patch` command with `-p1` option
- Performs dry-run validation before applying
- Saves patch artifact to `diffs/step_NNNN.patch`
- Emits `PATCH_APPLIED` event

**Error Types**:
- `patch_parse_error`: Invalid diff format
- `path_escape`: Patch targets file outside workspace
- `file_not_found`: Target file doesn't exist
- `patch_hunk_fail`: Context doesn't match (patch won't apply)
- `timeout`: Operation timed out (10s limit)

---

### run

**Purpose**: Execute a command in the sandbox.

**Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command` | `str` | (required) | Shell command to execute |
| `timeout_sec` | `int \| None` | `None` | Override default timeout |
| `env` | `dict[str, str] \| None` | `None` | Additional environment variables |

**Returns**: Exit code and paths to stdout/stderr.

**Example**:
```python
RunParams(command="pytest -q", timeout_sec=120)
# Returns: {
#     "exit_code": 0,
#     "stdout_path": "logs/tool_step_0005_stdout.txt",
#     "stderr_path": "logs/tool_step_0005_stderr.txt"
# }
```

**Behavior**:
- Commands run inside Docker with `network=none`
- stdout/stderr captured to artifact files
- Large output is truncated to 100KB

**Error Types**:
- `timeout`: Command exceeded timeout
- `sandbox_error`: Docker execution failed
- `abnormal_exit`: Non-zero exit code (not always an error)

## Event Logging

Every tool call emits events to `events.jsonl`:

| Event | When | Payload |
|-------|------|---------|
| `tool_call_started` | Before execution | `request_id`, `tool`, `params` |
| `tool_call_finished` | After execution | `request_id`, `tool`, `status`, `duration_sec` |

## Timeouts

| Tool | Default Timeout |
|------|-----------------|
| `list_files` | 30 seconds |
| `read_file` | 10 seconds |
| `search` | 60 seconds |
| `apply_patch` | 10 seconds |
| `run` | Configured per-task |

## Security

All tools enforce these security measures:

1. **Path containment**: All paths are resolved and verified to stay within workspace
2. **Symlink blocking**: Symlinks are rejected by default
3. **Network isolation**: Docker containers run with `network=none`
4. **Output limits**: Large outputs are truncated to prevent DoS
