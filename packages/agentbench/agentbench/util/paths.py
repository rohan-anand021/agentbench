from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """
      Function `ensure_dir(path: Path) -> Path`:
      creates directory if not exists, returns path
    - This is a simple helper used everywhere
    """

    path.mkdir(parents=True, exist_ok=True)
    return path
