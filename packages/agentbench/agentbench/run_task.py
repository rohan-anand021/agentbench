import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import ulid

from agentbench.sandbox.docker_sandbox import DockerSandbox
from agentbench.tasks.loader import load_task
from agentbench.util.git import checkout_commit, clone_repo
from agentbench.util.paths import ensure_dir
from agentbench.util.process import check_exit_code

logger = logging.getLogger(__name__)


def run_task(
    task_yaml: Path, out_dir: Path, str_format: str = "%Y-%m-%d_%H-%M-%S"
) -> Path:
    """
    ### Integrate with Existing Code
    - [ ] Refactor `run_task.py` to use `TaskSpec` from loader:
    - Change `run_task(task_yaml: Path, ...)` to internally use `load_task()`
    - Keep the function signature the same for CLI compatibility
    - Extract common logic (git clone, checkout) into helper functions in `agentbench/util/git.py`
    """

    logger.info("Loading task from %s", task_yaml)

    task = load_task(task_yaml)

    logger.debug("Task validated successfully: %s", task.id)

    out_dir = ensure_dir(out_dir)
    runs_dir = ensure_dir(Path(out_dir / "runs"))

    timestamp = datetime.now().strftime(str_format)
    run_id = str(ulid.new())

    logger.info("Starting run %s for task %s", run_id, task.id)

    curr_run_dir = ensure_dir(Path(runs_dir, f"{timestamp}__{run_id}"))

    task_dir = ensure_dir(Path(curr_run_dir, "task"))
    logs_dir = ensure_dir(Path(curr_run_dir, "logs"))
    workspace_dir = ensure_dir(Path(curr_run_dir, "workspace"))

    # copying task_yaml into task
    shutil.copy(task_yaml, task_dir)

    # create workspace/repo
    repo_dir = ensure_dir(Path(workspace_dir, "repo"))

    # clone the repo
    logger.info("Cloning repository from %s", task.repo.url)
    stdout_path, stderr_path, exit_code = clone_repo(
        url=task.repo.url, dest=repo_dir, logs_dir=logs_dir
    )

    error = check_exit_code("git_clone", exit_code)
    if error is not None:
        raise error

    logger.debug("Repository cloned successfully")

    # checkout the commit
    logger.info("Checking out commit %s", task.repo.commit)
    stdout_path, stderr_path, exit_code = checkout_commit(
        repo_dir=repo_dir, commit=task.repo.commit, logs_dir=logs_dir
    )

    error = check_exit_code("git_checkout", exit_code)
    if error is not None:
        raise error

    logger.debug("Commit checked out successfully")

    logger.info(
        "Initializing Docker sandbox with image %s",
        task.environment.docker_image,
    )
    sandbox = DockerSandbox(
        image=task.environment.docker_image,
        workdir=task.environment.workdir,
    )

    setup_commands = " && ".join(task.setup.commands)
    repo_relative_path = "repo"
    setup_commands = f"cd {repo_relative_path} && {setup_commands}"

    logger.info("Running setup commands")
    logger.debug("Setup commands: %s", setup_commands)
    setup_run_result = sandbox.run(
        workspace_host_path=workspace_dir,
        command=setup_commands,
        network="bridge",
        timeout_sec=task.environment.timeout_sec,
        stdout_path=Path(logs_dir, "setup_stdout.txt"),
        stderr_path=Path(logs_dir, "setup_stderr.txt"),
    )

    if setup_run_result.exit_code != 0:
        logger.error(
            "Setup failed with exit code %d", setup_run_result.exit_code
        )
        raise ValueError("Setup run failed, please try again")

    logger.debug("Setup completed successfully")

    run_cmd = task.run.command
    run_cmd = f"cd repo && {run_cmd}"

    logger.info("Running task command")
    logger.debug("Run command: %s", run_cmd)
    run_run_result = sandbox.run(
        workspace_host_path=workspace_dir,
        command=run_cmd,
        network="none",
        timeout_sec=task.environment.timeout_sec,
        stdout_path=Path(logs_dir, "run_stdout.txt"),
        stderr_path=Path(logs_dir, "run_stderr.txt"),
    )

    try:
        digest_cmd = subprocess.run(
            [
                "docker",
                "image",
                "inspect",
                task.environment.docker_image,
                "--format={{.Id}}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if digest_cmd.returncode != 0:
            err = digest_cmd.stderr.strip()
            image_digest = f"Image digest unavailable: {err}"
        else:
            image_digest = (
                digest_cmd.stdout.strip()
                or "Image digest unavailable: empty output"
            )

    except subprocess.TimeoutExpired as e:
        image_digest = f"Process timed out: {str(e)}"
    except OSError as e:
        image_digest = f"Docker unavailable: {str(e)}"

    run_data = {
        "run_id": run_id,
        "task_id": task.id,
        "repo_url": task.repo.url,
        "repo_commit": task.repo.commit,
        "docker_image": task.environment.docker_image,
        "docker_image_digest": image_digest,
        "network_settings": {"Setup": "bridge", "Run": "none"},
        "commands_executed": {
            "setup": task.setup.commands,
            "run": task.run.command,
        },
        "exit_codes": {
            "Setup exit code": str(setup_run_result.exit_code),
            "Run exit code": str(run_run_result.exit_code),
        },
        "paths_to_logs": str(logs_dir),
    }

    runs_path = Path(curr_run_dir, "run.json")
    with runs_path.open("w", encoding="utf-8") as runs:
        json.dump(run_data, runs, indent=2)

    logger.info(
        "Run completed (exit code: %s). Artifacts saved to %s",
        run_run_result.exit_code,
        curr_run_dir,
    )

    return curr_run_dir
