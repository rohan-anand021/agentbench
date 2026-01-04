import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from agentbench.tools.contract import (
    ApplyPatchParams,
    ToolError,
    ToolName,
    ToolResult,
    ToolStatus,
)
from agentbench.tools.patch_models import FilePatch, PatchHunk
from agentbench.sandbox.filesystem import resolve_safe_path

logger = logging.getLogger(__name__)

HUNK_HEADER_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchApplyError(Exception):
    pass


def _strict_patch_enabled() -> bool:
    return os.getenv("AGENTBENCH_STRICT_PATCH", "").lower() in {"1", "true", "yes"}


def _file_missing_trailing_newline(path: Path) -> tuple[bool, int | None]:
    try:
        data = path.read_bytes()
    except OSError:
        return False, None
    if data.endswith(b"\n"):
        return False, len(data.splitlines())
    return True, len(data.splitlines())


def _normalize_noeof_markers(patch_txt: str, workspace_root: Path) -> tuple[str, bool]:
    normalized_patch, normalized = _normalize_split_headers(patch_txt)
    patch_txt = normalized_patch
    lines = patch_txt.splitlines()
    out: list[str] = []
    changed = normalized

    current_old_path: str | None = None
    old_missing_newline = False
    old_last_line: int | None = None
    inserted_old = False
    pending_new_marker = False
    in_hunk = False
    old_line = 0
    new_line = 0

    for line in lines:
        if line.startswith("--- "):
            raw_old_path = line.split("--- ")[1]
            current_old_path = (
                raw_old_path
                if raw_old_path == "/dev/null"
                else raw_old_path.removeprefix("a/")
            )
            old_missing_newline = False
            old_last_line = None
            inserted_old = False
            in_hunk = False
            if current_old_path and current_old_path != "/dev/null":
                old_path = workspace_root / current_old_path
                old_missing_newline, old_last_line = _file_missing_trailing_newline(old_path)
            out.append(line)
            continue
        if line.startswith("+++ "):
            out.append(line)
            continue
        if line.startswith("@@ "):
            match = HUNK_HEADER_RE.match(line)
            if match:
                old_line = int(match.group(1))
                new_line = int(match.group(3))
                in_hunk = True
            out.append(line)
            continue

        if not in_hunk:
            out.append(line)
            continue

        if line.startswith("\\ No newline at end of file"):
            out.append(line)
            inserted_old = True
            continue

        if line.startswith(" ") or line.startswith("-"):
            if (
                old_missing_newline
                and not inserted_old
                and old_last_line
                and old_line == old_last_line
            ):
                out.append(line)
                out.append("\\ No newline at end of file")
                changed = True
                inserted_old = True
                pending_new_marker = True
            else:
                out.append(line)

            if line.startswith(" "):
                old_line += 1
                new_line += 1
            else:
                old_line += 1
            continue

        if line.startswith("+"):
            out.append(line)
            if pending_new_marker:
                out.append("\\ No newline at end of file")
                changed = True
                pending_new_marker = False
            new_line += 1
            continue

        out.append(line)

    return "\n".join(out), changed


def _normalize_hunk_counts(patch_txt: str) -> tuple[str, bool]:
    lines = patch_txt.splitlines()
    out: list[str] = []
    changed = False
    header: str | None = None
    hunk_lines: list[str] = []

    def flush_hunk() -> None:
        nonlocal changed, header, hunk_lines
        if header is None:
            return
        match = HUNK_HEADER_RE.match(header)
        if match:
            old_start = int(match.group(1))
            new_start = int(match.group(3))
            old_count = 0
            new_count = 0
            for hline in hunk_lines:
                if hline.startswith("\\ No newline at end of file"):
                    continue
                if hline.startswith(" ") or hline.startswith("-"):
                    old_count += 1
                if hline.startswith(" ") or hline.startswith("+"):
                    new_count += 1
            new_header = f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"
            if new_header != header:
                changed = True
            out.append(new_header)
        else:
            out.append(header)
        out.extend(hunk_lines)
        header = None
        hunk_lines = []

    for line in lines:
        if line.startswith("--- ") or line.startswith("+++ "):
            flush_hunk()
            out.append(line)
            continue
        if line.startswith("@@ "):
            flush_hunk()
            header = line
            hunk_lines = []
            continue
        if header is not None:
            hunk_lines.append(line)
        else:
            out.append(line)

    flush_hunk()
    return "\n".join(out), changed


def _normalize_patch_paths(
    patch_txt: str,
    workspace_root: Path | None = None,
) -> tuple[str, bool]:
    lines = patch_txt.splitlines()
    out: list[str] = []
    changed = False

    def _strip_workspace_prefix(path: str) -> str:
        for prefix in ("/workspace/repo/", "workspace/repo/"):
            if path.startswith(prefix):
                return path[len(prefix):]
        for prefix in ("/workspace/", "workspace/"):
            if path.startswith(prefix):
                remainder = path[len(prefix):]
                if remainder.startswith("repo/"):
                    remainder = remainder[len("repo/"):]
                return remainder
        return path

    for line in lines:
        if line.startswith("--- ") or line.startswith("+++ "):
            marker = line[:4]
            tail = line[4:]
            path_part, sep, rest = tail.partition("\t")
            if not sep:
                path_part, sep, rest = tail.partition(" ")
            path = path_part.strip()
            if path and path != "/dev/null":
                prefix = ""
                remainder = path
                if remainder.startswith("a/") or remainder.startswith("b/"):
                    prefix = remainder[:2]
                    remainder = remainder[2:]
                normalized = _strip_workspace_prefix(remainder)
                if workspace_root and normalized:
                    candidates = [normalized]
                    if normalized.startswith("repo/"):
                        candidates.append(normalized[len("repo/"):])
                    for candidate in candidates:
                        direct = workspace_root / candidate
                        src_candidate = workspace_root / "src" / candidate
                        repo_candidate = workspace_root / "repo" / candidate
                        repo_src_candidate = workspace_root / "repo" / "src" / candidate
                        if direct.exists():
                            normalized = candidate
                            break
                        if src_candidate.exists():
                            normalized = f"src/{candidate}"
                            changed = True
                            break
                        if repo_candidate.exists():
                            normalized = f"repo/{candidate}"
                            changed = True
                            break
                        if repo_src_candidate.exists():
                            normalized = f"repo/src/{candidate}"
                            changed = True
                            break
                if normalized != remainder:
                    changed = True
                path = f"{prefix}{normalized}"
            out.append(f"{marker}{path}{sep}{rest}")
            continue
        out.append(line)

    return "\n".join(out), changed


def _normalize_patch_headers(patch_txt: str) -> tuple[str, bool]:
    lines = patch_txt.splitlines()
    out: list[str] = []
    changed = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            changed = True
            continue

        if line.startswith(":--- ") or line.startswith(">--- "):
            line = line[1:]
            changed = True
        elif line.startswith(":+++ ") or line.startswith(">+++ "):
            line = line[1:]
            changed = True
        elif line.startswith(":@@ ") or line.startswith(">@@ "):
            line = line[1:]
            changed = True

        out.append(line)

    return "\n".join(out), changed


def _normalize_split_headers(patch_txt: str) -> tuple[str, bool]:
    lines = patch_txt.splitlines()
    out: list[str] = []
    changed = False
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped in ("---", "+++"):
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if next_line and not next_line.startswith(("---", "+++", "@@")):
                    out.append(f"{stripped} {next_line.lstrip()}")
                    changed = True
                    i += 2
                    continue
        out.append(line)
        i += 1

    return "\n".join(out), changed


def _normalize_hunk_prefixes(patch_txt: str) -> tuple[str, bool]:
    lines = patch_txt.splitlines()
    out: list[str] = []
    changed = False
    in_hunk = False

    for line in lines:
        if line.startswith("--- ") or line.startswith("+++ "):
            in_hunk = False
            out.append(line)
            continue
        if line.startswith("@@ "):
            in_hunk = True
            out.append(line)
            continue

        if in_hunk:
            if line.startswith((" ", "+", "-", "\\")):
                out.append(line)
            elif line == "":
                out.append(" ")
                changed = True
            else:
                out.append(f" {line}")
                changed = True
        else:
            out.append(line)

    return "\n".join(out), changed


def _parse_begin_patch(patch_txt: str) -> list[dict[str, object]]:
    lines = patch_txt.splitlines()
    if not lines or not lines[0].startswith("*** Begin Patch"):
        return []

    entries: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.startswith("*** End Patch"):
            if current:
                entries.append(current)
            break
        if line.startswith("*** Update File: "):
            if current:
                entries.append(current)
            current = {
                "action": "update",
                "path": line.split("*** Update File: ", 1)[1].strip(),
                "lines": [],
            }
        elif line.startswith("*** Add File: "):
            if current:
                entries.append(current)
            current = {
                "action": "add",
                "path": line.split("*** Add File: ", 1)[1].strip(),
                "lines": [],
            }
        elif line.startswith("*** Delete File: "):
            if current:
                entries.append(current)
            current = {
                "action": "delete",
                "path": line.split("*** Delete File: ", 1)[1].strip(),
                "lines": [],
            }
        elif line.startswith("*** Move to: "):
            if current is not None:
                current["move_to"] = line.split("*** Move to: ", 1)[1].strip()
        else:
            if current is not None:
                current["lines"].append(line)
        i += 1

    return entries


def _apply_begin_patch_lines(orig_lines: list[str], diff_lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    j = 0

    def find_next(start: int, text: str) -> int | None:
        for idx in range(start, len(orig_lines)):
            if orig_lines[idx] == text:
                return idx
        return None

    while j < len(diff_lines):
        line = diff_lines[j]
        if line.startswith("@@"):
            j += 1
            continue
        if line.startswith("\\ No newline at end of file"):
            j += 1
            continue
        if not line:
            out.append(line)
            j += 1
            continue

        prefix = line[0]
        content = line[1:] if prefix in (" ", "+", "-") else line

        if prefix == " ":
            if i < len(orig_lines) and orig_lines[i] == content:
                out.append(orig_lines[i])
                i += 1
                j += 1
                continue
            match_idx = find_next(i, content)
            if match_idx is None:
                raise PatchApplyError("Context line not found while applying patch.")
            out.extend(orig_lines[i:match_idx])
            i = match_idx
            out.append(orig_lines[i])
            i += 1
            j += 1
            continue
        if prefix == "-":
            if i < len(orig_lines) and orig_lines[i] == content:
                i += 1
                j += 1
                continue
            match_idx = find_next(i, content)
            if match_idx is None:
                raise PatchApplyError("Removal line not found while applying patch.")
            out.extend(orig_lines[i:match_idx])
            i = match_idx + 1
            j += 1
            continue
        if prefix == "+":
            out.append(content)
            j += 1
            continue

        out.append(line)
        j += 1

    out.extend(orig_lines[i:])
    return out


def _apply_begin_patch(
    patch_txt: str,
    workspace_root: Path,
) -> list[str]:
    entries = _parse_begin_patch(patch_txt)
    if not entries:
        raise PatchApplyError("No entries found in begin patch format.")

    changed_files: list[str] = []

    for entry in entries:
        action = entry.get("action")
        raw_path = str(entry.get("path") or "").strip()
        if not raw_path:
            raise PatchApplyError("Patch entry missing path.")

        path = resolve_safe_path(workspace_root, raw_path)
        move_to = entry.get("move_to")
        diff_lines = list(entry.get("lines") or [])

        if action == "delete":
            if path.exists():
                path.unlink()
                changed_files.append(raw_path)
            continue

        if action == "add":
            content_lines = []
            for line in diff_lines:
                if line.startswith("+"):
                    content_lines.append(line[1:])
                elif line.startswith(" "):
                    content_lines.append(line[1:])
                elif line.startswith("\\ No newline at end of file"):
                    continue
                else:
                    content_lines.append(line)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(content_lines) + "\n", encoding="utf-8", newline="\n")
            changed_files.append(raw_path)
            continue

        if action != "update":
            raise PatchApplyError(f"Unsupported patch action: {action}")

        if not path.exists():
            raise PatchApplyError(f"Patch target not found: {raw_path}")

        original_text = path.read_text(encoding="utf-8")
        ends_with_newline = original_text.endswith("\n")
        orig_lines = original_text.splitlines()
        updated_lines = _apply_begin_patch_lines(orig_lines, diff_lines)
        updated_text = "\n".join(updated_lines)
        if ends_with_newline or updated_text:
            updated_text += "\n"
        path.write_text(updated_text, encoding="utf-8", newline="\n")
        changed_files.append(raw_path)

        if move_to:
            move_target = resolve_safe_path(workspace_root, str(move_to))
            move_target.parent.mkdir(parents=True, exist_ok=True)
            path.replace(move_target)

    return changed_files


def _looks_like_context_patch(patch_txt: str) -> bool:
    for line in patch_txt.splitlines():
        if line.startswith("@@") and not HUNK_HEADER_RE.match(line):
            return True
    return False


def _parse_context_patch(patch_txt: str) -> list[dict[str, object]]:
    lines = patch_txt.splitlines()
    entries: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in lines:
        if line.startswith("--- "):
            if current:
                entries.append(current)
            raw_path = line.split("--- ", 1)[1].strip()
            path = raw_path if raw_path == "/dev/null" else raw_path.removeprefix("a/")
            current = {"path": path, "lines": []}
            continue
        if line.startswith("+++ "):
            if current is None:
                continue
            raw_path = line.split("+++ ", 1)[1].strip()
            path = raw_path if raw_path == "/dev/null" else raw_path.removeprefix("b/")
            current["path"] = path
            continue
        if line.startswith("@@"):
            if current is not None:
                current["lines"].append("@@")
            continue
        if current is not None:
            current["lines"].append(line)

    if current:
        entries.append(current)

    return entries


def _apply_context_patch(
    patch_txt: str,
    workspace_root: Path,
) -> list[str]:
    entries = _parse_context_patch(patch_txt)
    if not entries:
        raise PatchApplyError("No file entries found for context patch.")

    changed_files: list[str] = []
    for entry in entries:
        raw_path = str(entry.get("path") or "").strip()
        if not raw_path or raw_path == "/dev/null":
            continue
        path = resolve_safe_path(workspace_root, raw_path)
        if not path.exists():
            raise PatchApplyError(f"Patch target not found: {raw_path}")

        original_text = path.read_text(encoding="utf-8")
        ends_with_newline = original_text.endswith("\n")
        orig_lines = original_text.splitlines()
        diff_lines = list(entry.get("lines") or [])
        updated_lines = _apply_begin_patch_lines(orig_lines, diff_lines)
        updated_text = "\n".join(updated_lines)
        if ends_with_newline or updated_text:
            updated_text += "\n"
        path.write_text(updated_text, encoding="utf-8", newline="\n")
        changed_files.append(raw_path)

    return changed_files


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
            old_path = raw_old_path if raw_old_path == "/dev/null" else raw_old_path.removeprefix("a/")
        elif line.startswith("+++"):
            raw_new_path = line.split("+++ ")[1]
            new_path = raw_new_path if raw_new_path == "/dev/null" else raw_new_path.removeprefix("b/")
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

    logger.debug("Parsed %d file patches from unified diff", len(all_patches))
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

    if errors:
        logger.warning("Patch validation found %d errors", len(errors))
    return errors


def apply_patch(
    workspace_root: Path,
    params: ApplyPatchParams,
    step_id: int,
    artifacts_dir: Path
) -> ToolResult:

    started_at = datetime.now()
    request_id = f"patch_{step_id}"
    logger.debug("Applying patch at step %d", step_id)

    patch_text = params.unified_diff
    patch_file = None
    strict_patch = _strict_patch_enabled()

    def _write_patch(text: str) -> str:
        if text and not text.endswith("\n"):
            text = f"{text}\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
            f.write(text)
            return f.name

    if strict_patch and patch_text.lstrip().startswith("*** Begin Patch"):
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
                message="Strict patch mode rejects Begin Patch format.",
                details={},
            ),
        )

    if patch_text.lstrip().startswith("*** Begin Patch"):
        try:
            changed_files = _apply_begin_patch(patch_text, workspace_root)
        except PatchApplyError as exc:
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
                    message=str(exc),
                    details={},
                ),
            )

        artifact_path = artifacts_dir / f"step_{step_id:04d}.patch"
        artifact_path.write_text(patch_text, encoding="utf-8", newline="\n")
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
                "patch_size_bytes": len(patch_text.encode("utf-8")),
            },
        )

    if not strict_patch:
        normalized_patch, changed = _normalize_split_headers(patch_text)
        if changed:
            patch_text = normalized_patch

        normalized_patch, changed = _normalize_patch_headers(patch_text)
        if changed:
            patch_text = normalized_patch

        normalized_patch, changed = _normalize_hunk_prefixes(patch_text)
        if changed:
            patch_text = normalized_patch

        normalized_patch, changed = _normalize_patch_paths(
            patch_text,
            workspace_root=workspace_root,
        )
        if changed:
            patch_text = normalized_patch

    patch_file = _write_patch(patch_text)

    dry_run = subprocess.run(
        ["patch", "--batch", "--dry-run", "-p1", "-d", str(workspace_root), "-i", patch_file],
        capture_output=True,
        text=True,
    )

    if dry_run.returncode != 0 and not strict_patch:
        normalized_patch, changed = _normalize_hunk_counts(patch_text)
        if changed:
            patch_text = normalized_patch
            patch_file = _write_patch(patch_text)
            dry_run = subprocess.run(
                ["patch", "--batch", "--dry-run", "-p1", "-d", str(workspace_root), "-i", patch_file],
                capture_output=True,
                text=True,
            )

    if dry_run.returncode != 0 and not strict_patch:
        normalized_patch, changed = _normalize_noeof_markers(
            patch_text,
            workspace_root,
        )
        if changed:
            patch_text = normalized_patch
            patch_file = _write_patch(patch_text)
            dry_run = subprocess.run(
                ["patch", "--batch", "--dry-run", "-p1", "-d", str(workspace_root), "-i", patch_file],
                capture_output=True,
                text=True,
            )

    if dry_run.returncode != 0 and not strict_patch:
        if _looks_like_context_patch(patch_text):
            try:
                changed_files = _apply_context_patch(patch_text, workspace_root)
            except PatchApplyError as exc:
                logger.error("Patch dry-run failed: %s", dry_run.stderr)
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
                        message=str(exc),
                        details={"stderr": dry_run.stderr},
                    ),
                )

            artifact_path = artifacts_dir / f"step_{step_id:04d}.patch"
            artifact_path.write_text(patch_text, encoding="utf-8", newline="\n")
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
                    "patch_size_bytes": len(patch_text.encode("utf-8")),
                },
            )

        logger.error("Patch dry-run failed: %s", dry_run.stderr)
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
                details={"stderr": dry_run.stderr},
            ),
        )

    subprocess.run(
        ["patch", "--batch", "-p1", "-d", str(workspace_root), "-i", patch_file],
        capture_output=True,
        text=True,
    )

    artifact_path = artifacts_dir / f"step_{step_id:04d}.patch"
    shutil.copy(patch_file, artifact_path)

    patches = parse_unified_diff(patch_text)
    changed_files = [p.new_path for p in patches if p.new_path and p.new_path != "/dev/null"]
    logger.info("Patch applied successfully, changed %d files", len(changed_files))

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
