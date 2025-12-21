from pathlib import Path

from agentbench.util.process import run_command


def clone_repo(
    url: str, dest: Path, logs_dir: Path, timeout_sec: int = 120
) -> tuple[Path, Path, int]:
    cmd = ["git", "clone", url, str(dest)]

    return run_command(
        cmd_name="git_clone", cmd=cmd, timeout=timeout_sec, logs_dir=logs_dir
    )


def checkout_commit(
    repo_dir: Path, commit: str, logs_dir: Path, timeout_sec: int = 120
) -> tuple[Path, Path, int]:
    cmd = ["git", "checkout", commit]

    return run_command(
        cmd_name="git_checkout",
        cmd=cmd,
        timeout=timeout_sec,
        logs_dir=logs_dir,
        cwd=repo_dir,
    )
