import shlex
from pathlib import Path
from typing import Protocol

from agentbench.util.paths import ensure_dir
from agentbench.util.process import run_command


class _SandboxExec(Protocol):
    def exec(
        self,
        command: str,
        stdout_path: Path,
        stderr_path: Path,
        timeout_sec: int,
        network: str | None = None,
    ):
        ...


def _sandbox_log_paths(logs_dir: Path, cmd_name: str) -> tuple[Path, Path]:
    logs_dir = ensure_dir(logs_dir)
    stdout_path = Path(logs_dir, f"{cmd_name}_stdout.txt")
    stderr_path = Path(logs_dir, f"{cmd_name}_stderr.txt")
    return stdout_path, stderr_path


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


def status_porcelain(
    repo_dir: Path,
    logs_dir: Path,
    timeout_sec: int = 30,
    include_untracked: bool = False,
) -> tuple[Path, Path, int]:
    cmd = ["git", "status", "--porcelain"]
    if not include_untracked:
        cmd.append("--untracked-files=no")

    return run_command(
        cmd_name="post_setup_status",
        cmd=cmd,
        timeout=timeout_sec,
        logs_dir=logs_dir,
        cwd=repo_dir,
    )


def diff_stat(
    repo_dir: Path, logs_dir: Path, timeout_sec: int = 30
) -> tuple[Path, Path, int]:
    cmd = ["git", "diff", "--stat"]

    return run_command(
        cmd_name="post_setup_diff_stat",
        cmd=cmd,
        timeout=timeout_sec,
        logs_dir=logs_dir,
        cwd=repo_dir,
    )


def diff_patch(
    repo_dir: Path, logs_dir: Path, timeout_sec: int = 30
) -> tuple[Path, Path, int]:
    cmd = ["git", "diff"]

    return run_command(
        cmd_name="post_setup_diff",
        cmd=cmd,
        timeout=timeout_sec,
        logs_dir=logs_dir,
        cwd=repo_dir,
    )


def sandbox_clone(
    sandbox: _SandboxExec,
    repo_url: str,
    dest: str,
    logs_dir: Path,
    timeout_sec: int = 120,
) -> tuple[Path, Path, int]:
    stdout_path, stderr_path = _sandbox_log_paths(logs_dir, "git_clone")
    result = sandbox.exec(
        command=f"git clone {shlex.quote(repo_url)} {dest}",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_sec=timeout_sec,
        network="bridge",
    )
    return stdout_path, stderr_path, result.exit_code


def sandbox_checkout(
    sandbox: _SandboxExec,
    repo_dir: str,
    commit: str,
    logs_dir: Path,
    timeout_sec: int = 120,
) -> tuple[Path, Path, int]:
    stdout_path, stderr_path = _sandbox_log_paths(logs_dir, "git_checkout")
    result = sandbox.exec(
        command=f"cd {shlex.quote(repo_dir)} && git checkout {shlex.quote(commit)}",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_sec=timeout_sec,
        network="none",
    )
    return stdout_path, stderr_path, result.exit_code


def sandbox_status_porcelain(
    sandbox: _SandboxExec,
    repo_dir: str,
    logs_dir: Path,
    timeout_sec: int = 30,
    include_untracked: bool = False,
) -> tuple[Path, Path, int]:
    stdout_path, stderr_path = _sandbox_log_paths(
        logs_dir, "post_setup_status"
    )
    cmd = "git status --porcelain"
    if not include_untracked:
        cmd += " --untracked-files=no"
    result = sandbox.exec(
        command=f"cd {shlex.quote(repo_dir)} && {cmd}",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_sec=timeout_sec,
        network="none",
    )
    return stdout_path, stderr_path, result.exit_code


def sandbox_diff_stat(
    sandbox: _SandboxExec,
    repo_dir: str,
    logs_dir: Path,
    timeout_sec: int = 30,
) -> tuple[Path, Path, int]:
    stdout_path, stderr_path = _sandbox_log_paths(
        logs_dir, "post_setup_diff_stat"
    )
    result = sandbox.exec(
        command=f"cd {shlex.quote(repo_dir)} && git diff --stat",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_sec=timeout_sec,
        network="none",
    )
    return stdout_path, stderr_path, result.exit_code


def sandbox_diff_patch(
    sandbox: _SandboxExec,
    repo_dir: str,
    logs_dir: Path,
    timeout_sec: int = 30,
) -> tuple[Path, Path, int]:
    stdout_path, stderr_path = _sandbox_log_paths(
        logs_dir, "post_setup_diff"
    )
    result = sandbox.exec(
        command=f"cd {shlex.quote(repo_dir)} && git diff",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_sec=timeout_sec,
        network="none",
    )
    return stdout_path, stderr_path, result.exit_code


def ensure_git_in_sandbox(
    sandbox: _SandboxExec,
    logs_dir: Path,
    timeout_sec: int = 180,
) -> bool:
    """
    Ensure git is available inside the sandbox by attempting installation via common package managers.
    Returns True if git is present or successfully installed, False otherwise.
    """
    check_stdout, check_stderr = _sandbox_log_paths(logs_dir, "git_check")
    check = sandbox.exec(
        command="command -v git",
        stdout_path=check_stdout,
        stderr_path=check_stderr,
        timeout_sec=15,
        network="bridge",
    )
    if check.exit_code == 0:
        return True

    install_commands = [
        "apt-get update && apt-get install -y git",
        "apk add --no-cache git",
        "yum install -y git",
        "dnf install -y git",
    ]

    for idx, cmd in enumerate(install_commands):
        install_stdout, install_stderr = _sandbox_log_paths(
            logs_dir, f"git_install_{idx}"
        )
        install_result = sandbox.exec(
            command=cmd,
            stdout_path=install_stdout,
            stderr_path=install_stderr,
            timeout_sec=timeout_sec,
            network="bridge",
        )
        if install_result.exit_code == 0:
            # Re-check
            check_after_stdout, check_after_stderr = _sandbox_log_paths(
                logs_dir, f"git_check_after_{idx}"
            )
            check_after = sandbox.exec(
                command="command -v git",
                stdout_path=check_after_stdout,
                stderr_path=check_after_stderr,
                timeout_sec=15,
                network="bridge",
            )
            if check_after.exit_code == 0:
                return True
    return False
