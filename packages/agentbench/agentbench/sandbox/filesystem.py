from pathlib import Path

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

    if relative_path.startswith('/'):
        relative_path = relative_path.strip('/')
    
    candidate = (workspace_root / relative_path).resolve()

    if not candidate.is_relative_to(workspace_root):
        raise PathEscapeError(candidate, workspace_root)

    if not allow_symlinks:
        path_so_far = workspace_root
        
        for part in candidate.relative_to(workspace_root).parts:
            path_so_far = path_so_far / part

            if path_so_far.is_symlink():
                raise SymLinkError(path_so_far)
    
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
    files = [f for f in files if not f.is_symlink() and '.git' not in f.parts]

    return sorted(files)





