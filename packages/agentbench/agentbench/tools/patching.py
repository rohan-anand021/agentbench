from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import subprocess
import tempfile
import shutil

from agentbench.tools.contract import ToolResult, ApplyPatchParams, ToolError, ToolStatus, ToolName

@dataclass
class PatchHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]

@dataclass
class FilePatch:
    old_path: str | None
    new_path: str | None
    hunks: list[PatchHunk]

def parse_unified_diff(patch_txt: str) -> list[FilePatch]:
    """
    Args:
        patch_txt (str): _description_

    Returns:
        list[FilePatch]: _description_

    A unified diff looks like:
    ```diff
    --- a/src/main.py
    +++ b/src/main.py
    @@ -10,6 +10,7 @@
    def calculate_total(items):
        total = 0
        for item in items:
    +        if item < 0:
    +            continue
            total += item
        return total
    ```

    **Key elements:**
    - `--- a/path` and `+++ b/path`: Source and destination files
    - `@@ -start,count +start,count @@`: Hunk header (line numbers)
    - Lines starting with `-`: Lines to remove
    - Lines starting with `+`: Lines to add
    - Lines starting with ` ` (space): Context lines (must match)
    """

    all_patches = []
    file_lines = []
    old_path = None
    new_path = None
    old_start = 0
    old_count = 0
    new_start = 0
    new_count = 0

    patch_split = patch_txt.split("\n")
    for line in patch_split:
        if line.startswith("---"):
            if old_path is not None:
                file_patch = FilePatch(
                    old_path = old_path,
                    new_path = new_path,
                    hunks = [PatchHunk(
                        old_start = old_start,
                        old_count = old_count,
                        new_start = new_start,
                        new_count = new_count,
                        lines = file_lines
                    )]
                )
                all_patches.append(file_patch) 
                file_lines = []
            raw_old_path = line.split("--- ")[1]
            old_path = raw_old_path if raw_old_path == "/dev/null" else raw_old_path.lstrip("a/")
        elif line.startswith("+++"):
            raw_new_path = line.split("+++ ")[1]
            new_path = raw_new_path if raw_new_path == "/dev/null" else raw_new_path.lstrip("b/")
        elif line.startswith("@@"):
            line_nums = line.replace("@@", "").strip()
            hunks = line_nums.split(" ")
            old_start, old_count = abs(int(hunks[0].split(",")[0])), abs(int(hunks[0].split(",")[1]))
            new_start, new_count = abs(int(hunks[1].split(",")[0])), abs(int(hunks[1].split(",")[1]))
        else:
            file_lines.append(line)
    
    if old_path is not None:
        file_patch = FilePatch(
            old_path = old_path,
            new_path = new_path,
            hunks = [PatchHunk(
                old_start = old_start,
                old_count = old_count,
                new_start = new_start,
                new_count = new_count,
                lines = file_lines
            )]
        )
        all_patches.append(file_patch)
    
    return all_patches


def validate_patch(
    workspace_root: Path,
    patches: list[FilePatch]
) -> list[str]:
    """_summary_

    Args:
        workspace_root (Path): _description_
        patches (list[FilePatch]): _description_

    Returns:
        list[str]: _description_

    **Validation checks:**

    | Check | Error if... |
    |-------|-------------|
    | Path escape | Any file path escapes workspace root |
    | File exists | Old file doesn't exist (unless new file) |
    | Context matches | Context lines don't match actual file content |
    | Hunk offset | Hunk line numbers are way off (fuzz limit) |
    | Encoding | File contains invalid UTF-8 |
    """

    errors: list[str] = []
    
    FUZZ_LIMIT = 3
    
    for patch in patches:
        old_path = patch.old_path
        new_path = patch.new_path
        is_new_file = old_path == "/dev/null" or old_path is None
        
        if old_path and old_path != "/dev/null":
            old_full = workspace_root / old_path
            if not old_full.resolve().is_relative_to(workspace_root.resolve()):
                errors.append(f"{old_path} escapes workspace root")
                continue
                
        if new_path and new_path != "/dev/null":
            new_full = workspace_root / new_path
            if not new_full.resolve().is_relative_to(workspace_root.resolve()):
                errors.append(f"{new_path} escapes workspace root")
                continue
        
        if not is_new_file and old_path:
            old_full = workspace_root / old_path
            if not old_full.exists():
                errors.append(f"{old_path} does not exist")
                continue
            
            try:
                file_content = old_full.read_text(encoding="utf-8")
                file_lines = file_content.splitlines()
            except UnicodeDecodeError:
                errors.append(f"{old_path} contains invalid UTF-8 encoding")
                continue
            
            for hunk in patch.hunks:
                hunk_start = hunk.old_start - 1
                
                if hunk_start < 0 or hunk_start > len(file_lines) + FUZZ_LIMIT:
                    errors.append(f"{old_path}: hunk at line {hunk.old_start} is outside file bounds (fuzz limit {FUZZ_LIMIT})")
                    continue
                
                expected_lines = []
                for line in hunk.lines:
                    if line.startswith(" ") or line.startswith("-"):
                        expected_lines.append(line[1:])
                
                if expected_lines:
                    matched = False
                    for offset in range(-FUZZ_LIMIT, FUZZ_LIMIT + 1):
                        adjusted_start = hunk_start + offset
                        if adjusted_start < 0:
                            continue
                        actual_slice = file_lines[adjusted_start:adjusted_start + len(expected_lines)]
                        if actual_slice == expected_lines:
                            matched = True
                            break
                    
                    if not matched:
                        errors.append(f"{old_path}: context at line {hunk.old_start} does not match file content")

    return errors


def apply_patch(
    workspace_root: Path,
    params: ApplyPatchParams,
    step_id: int,
    artifacts_dir: Path
) -> ToolResult:

    started_at = datetime.now()
    request_id = f"patch_{step_id}"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
        f.write(params.unified_diff)
        patch_file = f.name
    
    dry_run = subprocess.run(
        ["patch", 
        "--dry-run", 
        "-p1", 
        "-d", 
        str(workspace_root), 
        "-i", 
        patch_file],
        capture_output=True,
        text=True
    )

    if dry_run.returncode != 0:
        ended_at = datetime.now()

        return ToolResult(
            request_id=request_id,
            tool=ToolName.APPLY_PATCH,
            status=ToolStatus.ERROR,
            started_at=started_at,
            ended_at=ended_at,
            duration_sec=(ended_at - started_at).total_seconds(),
            error=ToolError(
                error_type="patch_hunk_fail",
                message="Patch does not apply cleanly",
                details={"stderr": dry_run.stderr}
            )
        )
    
    subprocess.run(
        ["patch", 
        "-p1", 
        "-d", 
        str(workspace_root), 
        "-i", 
        patch_file],
        capture_output=True,
        text=True
    )

    artifact_path = artifacts_dir / f"step_{step_id:04d}.patch"
    shutil.copy(patch_file, artifact_path)

    patches = parse_unified_diff(params.unified_diff)
    changed_files = [p.new_path for p in patches if p.new_path and p.new_path != "/dev/null"]

    ended_at = datetime.now()
    
    return ToolResult(
        request_id=request_id,
        tool=ToolName.APPLY_PATCH,
        status=ToolStatus.SUCCESS,
        started_at=started_at,
        ended_at=ended_at,
        duration_sec=(ended_at - started_at).total_seconds(),
        data={
            "changed_files": changed_files,
            "patch_size_bytes": len(params.unified_diff.encode('utf-8'))
        }
    )
