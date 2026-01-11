import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import ulid

from agentbench.sandbox import DockerRunResult, DockerSandbox
from agentbench.sandbox.persistent_sandbox import PersistentDockerSandbox
from agentbench.tasks.loader import load_task
from agentbench.util.git import (
    checkout_commit,
    clone_repo,
    diff_stat,
    sandbox_checkout,
    sandbox_clone,
    sandbox_diff_stat,
    ensure_git_in_sandbox,
)
from agentbench.util.paths import ensure_dir
from agentbench.util.process import check_exit_code

logger = logging.getLogger(__name__)

ALLOWED_SANDBOX_MODES = {"bind", "ephemeral"}


def _resolve_repo_url(repo_url: str, task_source_path: Path) -> str:
    if repo_url.startswith("file://"):
        return repo_url

    path_candidate = Path(repo_url)
    if path_candidate.is_absolute():
        return str(path_candidate)

    if repo_url.startswith("."):
        return str((task_source_path.parent / repo_url).resolve())

    base = task_source_path.parent.resolve()
    while True:
        candidate = base / repo_url
        if candidate.exists():
            return str(candidate.resolve())
        if base == base.parent:
            break
        base = base.parent

    return repo_url


def _inspect_docker_image(image: str) -> dict[str, object]:
    try:
        inspect_result = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if inspect_result.returncode != 0:
            return {
                "error": inspect_result.stderr.strip()
                or "Image inspect failed with no stderr output",
                "image_id": None,
                "repo_digests": [],
            }

        raw_payload = inspect_result.stdout.strip()
        if not raw_payload:
            return {
                "error": "Image inspect returned empty output",
                "image_id": None,
                "repo_digests": [],
            }

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as e:
            return {
                "error": f"Image inspect JSON parse failed: {e}",
                "image_id": None,
                "repo_digests": [],
            }

        return {
            "error": None,
            "image_id": payload.get("Id"),
            "repo_digests": payload.get("RepoDigests") or [],
        }
    except subprocess.TimeoutExpired as e:
        return {
            "error": f"Image inspect timed out: {e}",
            "image_id": None,
            "repo_digests": [],
        }
    except OSError as e:
        return {
            "error": f"Docker unavailable: {e}",
            "image_id": None,
            "repo_digests": [],
        }


def run_task(
    task_yaml: Path,
    out_dir: Path,
    sandbox_mode: str = "bind",
    str_format: str = "%Y-%m-%d_%H-%M-%S",
) -> Path:
    logger.info("Loading task from %s", task_yaml)
    if sandbox_mode not in ALLOWED_SANDBOX_MODES:
        raise ValueError(f"Unsupported sandbox mode: {sandbox_mode}")

    task = load_task(task_yaml)
    logger.debug("Task validated successfully: %s", task.id)

    out_dir = ensure_dir(out_dir)
    runs_dir = ensure_dir(Path(out_dir / "runs"))

    timestamp = datetime.now().strftime(str_format)
    run_id = str(ulid.ULID())

    logger.info("Starting run %s for task %s", run_id, task.id)

    curr_run_dir = ensure_dir(Path(runs_dir, f"{timestamp}__{run_id}"))

    task_dir = ensure_dir(Path(curr_run_dir, "task"))
    logs_dir = ensure_dir(Path(curr_run_dir, "logs"))
    workspace_dir = ensure_dir(Path(curr_run_dir, "workspace"))

    # Copy task_yaml into task dir for provenance
    shutil.copy(task_yaml, task_dir)

    task_source_path = task_yaml
    if isinstance(getattr(task, "source_path", None), Path):
        task_source_path = task.source_path

    repo_url_original = task.repo.url
    repo_url_resolved = _resolve_repo_url(repo_url_original, task_source_path)

    if repo_url_resolved != repo_url_original:
        logger.info(
            "Resolved repo URL from %s to %s",
            repo_url_original,
            repo_url_resolved,
        )

    image_metadata = _inspect_docker_image(task.environment.docker_image)

    # Common paths
    repo_relative_path = "repo"
    container_repo_path = f"{task.environment.workdir.rstrip('/')}/{repo_relative_path}"

    setup_stdout_path = Path(logs_dir, "setup_stdout.txt")
    setup_stderr_path = Path(logs_dir, "setup_stderr.txt")
    env_stdout_path = Path(logs_dir, "post_setup_env_stdout.txt")
    env_stderr_path = Path(logs_dir, "post_setup_env_stderr.txt")
    run_stdout_path = Path(logs_dir, "run_stdout.txt")
    run_stderr_path = Path(logs_dir, "run_stderr.txt")
    run_network = "bridge" if ("network" in (task.labels or [])) else "none"

    sandbox = None
    setup_run_result = None
    env_run_result = None
    run_run_result = None
    diff_stdout_path = None
    diff_stderr_path = None
    diff_exit_code = -1

    try:
        if sandbox_mode == "bind":
            repo_dir = ensure_dir(Path(workspace_dir, repo_relative_path))
            logger.info("Cloning repository from %s", repo_url_resolved)
            stdout_path, stderr_path, exit_code = clone_repo(
                url=repo_url_resolved, dest=repo_dir, logs_dir=logs_dir
            )
            error = check_exit_code("git_clone", exit_code)
            if error is not None:
                raise error

            logger.info("Checking out commit %s", task.repo.commit)
            stdout_path, stderr_path, exit_code = checkout_commit(
                repo_dir=repo_dir, commit=task.repo.commit, logs_dir=logs_dir
            )
            error = check_exit_code("git_checkout", exit_code)
            if error is not None:
                raise error

            sandbox = DockerSandbox(
                image=task.environment.docker_image,
                workdir=task.environment.workdir,
            )

            setup_commands = " && ".join(task.setup.commands)
            if setup_commands.strip():
                setup_commands = f"cd {repo_relative_path} && {setup_commands}"
                logger.info("Running setup commands")
                logger.debug("Setup commands: %s", setup_commands)
                setup_run_result = sandbox.run(
                    workspace_host_path=workspace_dir,
                    command=setup_commands,
                    network="bridge",
                    timeout_sec=task.environment.timeout_sec,
                    stdout_path=setup_stdout_path,
                    stderr_path=setup_stderr_path,
                )
            else:
                logger.info("No setup commands provided; skipping setup")
                setup_stdout_path.write_text(
                    "Setup skipped: no commands provided.\n",
                    encoding="utf-8",
                    newline="\n",
                )
                setup_stderr_path.write_text(
                    "", encoding="utf-8", newline="\n"
                )
                setup_run_result = DockerRunResult(
                    exit_code=0,
                    stdout_path=setup_stdout_path,
                    stderr_path=setup_stderr_path,
                    docker_cmd=[],
                )

            if setup_run_result.exit_code != 0:
                logger.error(
                    "Setup failed with exit code %d",
                    setup_run_result.exit_code,
                )
                raise ValueError("Setup run failed, please try again")

            logger.debug("Setup completed successfully")

            logger.info("Recording post-setup git diff --stat")
            diff_stdout_path, diff_stderr_path, diff_exit_code = diff_stat(
                repo_dir=repo_dir, logs_dir=logs_dir
            )
            if diff_exit_code != 0:
                logger.warning(
                    "Post-setup git diff --stat failed with exit code %d",
                    diff_exit_code,
                )

            logger.info("Capturing post-setup environment info")
            env_capture_cmd = (
                "uname -a || true; "
                "python -VV || true; "
                "pip --version || true; "
                "pytest --version || true"
            )
            env_run_result = sandbox.run(
                workspace_host_path=workspace_dir,
                command=env_capture_cmd,
                network="none",
                timeout_sec=min(task.environment.timeout_sec, 60),
                stdout_path=env_stdout_path,
                stderr_path=env_stderr_path,
            )
            if env_run_result.exit_code != 0:
                logger.warning(
                    "Post-setup environment capture failed with exit code %d",
                    env_run_result.exit_code,
                )

            run_cmd = f"cd {repo_relative_path} && {task.run.command}"
            logger.info("Running task command")
            logger.debug("Run command: %s", run_cmd)
            run_run_result = sandbox.run(
                workspace_host_path=workspace_dir,
                command=run_cmd,
                network=run_network,
                timeout_sec=task.environment.timeout_sec,
                stdout_path=run_stdout_path,
                stderr_path=run_stderr_path,
            )
        else:
            sandbox = PersistentDockerSandbox(
                image=task.environment.docker_image,
                workdir=task.environment.workdir,
            )
            sandbox.start()

            if not ensure_git_in_sandbox(sandbox=sandbox, logs_dir=logs_dir):
                raise RuntimeError(
                    "git is not available in sandbox and installation attempts failed"
                )

            # Ensure workspace/repo exists inside container
            sandbox.exec(
                command=f"mkdir -p {repo_relative_path}",
                stdout_path=setup_stdout_path,
                stderr_path=setup_stderr_path,
                timeout_sec=30,
                network="none",
            )

            repo_url_for_clone = repo_url_resolved
            local_repo_path = None
            if repo_url_resolved.startswith("file://"):
                local_repo_path = Path(repo_url_resolved[len("file://") :])
            else:
                candidate = Path(repo_url_resolved)
                if candidate.exists():
                    local_repo_path = candidate

            if local_repo_path and local_repo_path.exists():
                container_src = (
                    f"{task.environment.workdir.rstrip('/')}/src_repo"
                )
                logger.info(
                    "Copying local repo %s into sandbox at %s",
                    local_repo_path,
                    container_src,
                )
                sandbox.copy_to(local_repo_path, container_src)
                repo_url_for_clone = container_src

            logger.info("Cloning repository from %s (in sandbox)", repo_url_for_clone)
            stdout_path, stderr_path, exit_code = sandbox_clone(
                sandbox=sandbox,
                repo_url=repo_url_for_clone,
                dest=repo_relative_path,
                logs_dir=logs_dir,
                timeout_sec=task.environment.timeout_sec,
            )
            error = check_exit_code("git_clone", exit_code)
            if error is not None:
                raise error

            logger.info("Checking out commit %s (in sandbox)", task.repo.commit)
            stdout_path, stderr_path, exit_code = sandbox_checkout(
                sandbox=sandbox,
                repo_dir=repo_relative_path,
                commit=task.repo.commit,
                logs_dir=logs_dir,
                timeout_sec=task.environment.timeout_sec,
            )
            error = check_exit_code("git_checkout", exit_code)
            if error is not None:
                raise error

            setup_commands = " && ".join(task.setup.commands)
            if setup_commands.strip():
                setup_commands = f"cd {repo_relative_path} && {setup_commands}"
                logger.info("Running setup commands (sandbox)")
                logger.debug("Setup commands: %s", setup_commands)
                setup_run_result = sandbox.exec(
                    command=setup_commands,
                    stdout_path=setup_stdout_path,
                    stderr_path=setup_stderr_path,
                    network="bridge",
                    timeout_sec=task.environment.timeout_sec,
                )
            else:
                logger.info("No setup commands provided; skipping setup")
                setup_stdout_path.write_text(
                    "Setup skipped: no commands provided.\n",
                    encoding="utf-8",
                    newline="\n",
                )
                setup_stderr_path.write_text(
                    "", encoding="utf-8", newline="\n"
                )
                setup_run_result = DockerRunResult(
                    exit_code=0,
                    stdout_path=setup_stdout_path,
                    stderr_path=setup_stderr_path,
                    docker_cmd=[],
                )

            if setup_run_result.exit_code != 0:
                logger.error(
                    "Setup failed with exit code %d",
                    setup_run_result.exit_code,
                )
                raise ValueError("Setup run failed, please try again")

            logger.debug("Setup completed successfully")

            logger.info("Recording post-setup git diff --stat (sandbox)")
            diff_stdout_path, diff_stderr_path, diff_exit_code = sandbox_diff_stat(
                sandbox=sandbox,
                repo_dir=repo_relative_path,
                logs_dir=logs_dir,
            )
            if diff_exit_code != 0:
                logger.warning(
                    "Post-setup git diff --stat failed with exit code %d",
                    diff_exit_code,
                )

            logger.info("Capturing post-setup environment info (sandbox)")
            env_capture_cmd = (
                "uname -a || true; "
                "python -VV || true; "
                "pip --version || true; "
                "pytest --version || true"
            )
            env_run_result = sandbox.exec(
                command=env_capture_cmd,
                network="none",
                timeout_sec=min(task.environment.timeout_sec, 60),
                stdout_path=env_stdout_path,
                stderr_path=env_stderr_path,
            )
            if env_run_result.exit_code != 0:
                logger.warning(
                    "Post-setup environment capture failed with exit code %d",
                    env_run_result.exit_code,
                )

            run_cmd = f"cd {repo_relative_path} && {task.run.command}"
            logger.info("Running task command (sandbox)")
            logger.debug("Run command: %s", run_cmd)
            run_run_result = sandbox.exec(
                command=run_cmd,
                network=run_network,
                timeout_sec=task.environment.timeout_sec,
                stdout_path=run_stdout_path,
                stderr_path=run_stderr_path,
            )
    finally:
        if isinstance(sandbox, PersistentDockerSandbox):
            sandbox.cleanup()

    run_data = {
        "run_id": run_id,
        "task_id": task.id,
        "repo_url": repo_url_resolved,
        "repo_url_original": repo_url_original,
        "repo_commit": task.repo.commit,
        "docker_image": task.environment.docker_image,
        "docker_image_id": image_metadata["image_id"],
        "docker_image_repo_digests": image_metadata["repo_digests"],
        "docker_image_inspect_error": image_metadata["error"],
        "network_settings": {"Setup": "bridge", "Run": run_network},
        "commands_executed": {
            "setup": task.setup.commands,
            "run": task.run.command,
        },
        "exit_codes": {
            "Setup exit code": str(setup_run_result.exit_code if setup_run_result else -1),
            "Run exit code": str(run_run_result.exit_code if run_run_result else -1),
        },
        "post_setup_diff_stat": {
            "stdout_path": str(diff_stdout_path) if diff_stdout_path else "",
            "stderr_path": str(diff_stderr_path) if diff_stderr_path else "",
            "exit_code": str(diff_exit_code),
        },
        "post_setup_environment": {
            "command": env_capture_cmd,
            "stdout_path": str(env_stdout_path),
            "stderr_path": str(env_stderr_path),
            "exit_code": str(env_run_result.exit_code if env_run_result else -1),
        },
        "docker_run_args": {
            "setup": setup_run_result.docker_cmd if setup_run_result else [],
            "post_setup_environment": env_run_result.docker_cmd if env_run_result else [],
            "run": run_run_result.docker_cmd if run_run_result else [],
        },
        "paths_to_logs": str(logs_dir),
        "sandbox": {
            "mode": sandbox_mode,
            "container_id": getattr(sandbox, "container_id", None)
            if sandbox
            else None,
            "workspace": container_repo_path if sandbox_mode == "ephemeral" else str(workspace_dir),
        },
    }

    runs_path = Path(curr_run_dir, "run.json")
    with runs_path.open("w", encoding="utf-8") as runs:
        json.dump(run_data, runs, indent=2)

    logger.info(
        "Run completed (exit code: %s). Artifacts saved to %s",
        run_run_result.exit_code if run_run_result else "unknown",
        curr_run_dir,
    )

    return curr_run_dir
