import json
import logging
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from filelock import FileLock

logger = logging.getLogger(__name__)


def append_jsonl(path: Path, record: dict[str, Any] | str) -> bool:
    """
    Append a record to a JSONL file (dict or JSON string).

    - Open file in append mode
    - Write JSON + newline
    - Use file locking for concurrent writes

    Returns:
        True if write succeeded, False if write failed (e.g., disk full).
    """

    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        lock = FileLock(str(path) + ".lock")

        with lock:
            if isinstance(record, str):
                json_line = record if record.endswith("\n") else record + "\n"
            else:
                json_line = json.dumps(record) + "\n"
            with open(path, "ab") as f:
                f.write(json_line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())

        return True

    except OSError as e:
        print(f"CRITICAL: Failed to write to {path}: {e}", file=sys.stderr)
        logger.critical("Failed to write JSONL record to %s: %s", path, e)

        return False


def read_jsonl(path: Path) -> Iterator[dict]:
    """
    Function `read_jsonl(path: Path) -> Iterator[dict]`:
        - Open file, yield one parsed dict per line
        - Skip empty lines
        - Log warning (don't crash) for malformed lines
    """

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line == "":
                continue

            try:
                record = json.loads(line)
                yield record

            except Exception as e:
                logger.warning("Line %s could not be read: %s", line, str(e))
                continue
