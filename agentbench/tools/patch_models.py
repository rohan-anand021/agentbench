from dataclasses import dataclass


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
