import re
from typing import Iterable

_PIP_INSTALL_RE = re.compile(r"\bpip(?:3)?\s+install\b")
_PIP_TARGET_RE = re.compile(r"(?:^|\s)(--target|-t)\b")
_PIP_EDITABLE_RE = re.compile(r"(?:^|\s)(-e|--editable)\b")
_PIP_UPGRADE_RE = re.compile(r"(?:^|\s)(--upgrade|-U)\b")
_PIP_FORCE_REINSTALL_RE = re.compile(r"(?:^|\s)(--force-reinstall)\b")


def normalize_setup_commands(
    commands: Iterable[str],
    target_dir: str = "/workspace/site-packages",
    run_command: str | None = None,
) -> list[str]:
    """
    Ensure pip installs persist across container runs by adding --target
    when a pip install command does not already specify a target.
    """
    use_target = True
    if run_command is not None and target_dir:
        if target_dir not in run_command:
            use_target = False

    normalized: list[str] = []
    for command in commands:
        if not _PIP_INSTALL_RE.search(command):
            normalized.append(command)
            continue
        has_editable = _PIP_EDITABLE_RE.search(command) is not None
        has_target = _PIP_TARGET_RE.search(command) is not None
        has_upgrade = _PIP_UPGRADE_RE.search(command) is not None
        has_force = _PIP_FORCE_REINSTALL_RE.search(command) is not None

        if has_editable:
            normalized.append(command)
            continue

        if use_target and not has_target:
            command = f"{command} --target={target_dir}"
            has_target = True

        if has_target and not has_upgrade:
            command = f"{command} --upgrade"
        if has_target and not has_force:
            command = f"{command} --force-reinstall"

        normalized.append(command)
    return normalized
