import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PathEscapeError(Exception):
    def __init__(self, candidate: Path, workspace_root: Path):
        super().__init__(f"Candidate {str(candidate)} is not relative to workspace: {str(workspace_root)}")

class SymLinkError(Exception):
    def __init__(self, path: Path):
        super().__init__(f"Path contains symlink: {str(path)}")

def resolve_safe_path(
    workspace_root: Path,
    relative_path: str,
    allow_symlinks: bool = False
) -> Path:
    """
    Resolve a relative path within a workspace root safely.

    Args:
        workspace_root: Absolute path to the sandbox workspace
        relative_path: User-provided path (should be relative)
        allow_symlinks: If False, reject paths that contain symlinks

    Returns:
        Resolved absolute Path that is guaranteed to be within workspace_root

    Raises:
        PathEscapeError: If the resolved path would escape the workspace
        SymlinkError: If symlinks are not allowed and path contains one
    """

    workspace_root = Path(workspace_root).resolve()
    workspace_prefix = "/workspace"
    repo_prefix = "/workspace/repo"

    if relative_path == "repo":
        relative_path = ""
    elif relative_path.startswith("repo/"):
        relative_path = relative_path[len("repo/"):]
    elif relative_path == repo_prefix:
        relative_path = ""
    elif relative_path.startswith(f"{repo_prefix}/"):
        relative_path = relative_path[len(repo_prefix) + 1:]
    elif relative_path == workspace_prefix:
        relative_path = ""
    elif relative_path.startswith(f"{workspace_prefix}/"):
        relative_path = relative_path[len(workspace_prefix) + 1:]
    elif relative_path.startswith('/'):
        relative_path = relative_path.strip('/')

    candidate = (workspace_root / relative_path).resolve()

    if not candidate.is_relative_to(workspace_root):
        logger.warning("Path escape attempt: %s is not relative to %s", candidate, workspace_root)
        raise PathEscapeError(candidate, workspace_root)

    if not allow_symlinks:
        path_so_far = workspace_root

        for part in candidate.relative_to(workspace_root).parts:
            path_so_far = path_so_far / part

            if path_so_far.is_symlink():
                logger.warning("Symlink blocked: %s", path_so_far)
                raise SymLinkError(path_so_far)

    logger.debug("Resolved safe path: %s -> %s", relative_path, candidate)
    return candidate


def safe_glob(
    workspace_root: Path,
    pattern: str
) -> list[Path]:
    """
    Glob files within workspace root, returning only safe paths.

    Filters out:
    - Paths that escape workspace (shouldn't happen with proper glob)
    - Hidden directories like .git by default
    - Symlinks if not allowed
    """

    workspace_root = Path(workspace_root).resolve()

    files = list(workspace_root.glob(pattern))
    ignored_parts = {".git", ".pytest_cache", "__pycache__", "build"}
    filtered = []
    for f in files:
        if f.is_symlink():
            continue
        parts = f.parts
        if any(part in ignored_parts or part.startswith(".") for part in parts):
            continue
        filtered.append(f)
    files = filtered

    logger.debug("safe_glob matched %d files for pattern %s", len(files), pattern)
    return sorted(files)

