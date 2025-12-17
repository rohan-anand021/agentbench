from pathlib import Path
import logging
import time

from agentbench.tasks.models import ValidationResult, TaskSpec
from agentbench.util.paths import ensure_dir
from agentbench.util.git import clone_repo, checkout_commit
from agentbench.util.process import check_exit_code
from agentbench.sandbox.docker_sandbox import DockerSandbox

logger = logging.getLogger(__name__)

def validate_baseline(task: TaskSpec, 
                      workspace_dir: Path, 
                      logs_dir: Path) -> ValidationResult:
    """
    Function `validate_baseline(task: TaskSpec, workspace_dir: Path, logs_dir: Path) -> ValidationResult`:
        - Create workspace directory structure
        - Clone repo to `workspace/repo/`
        - Checkout pinned commit
        - Run setup commands with `network=bridge`
        - Run the `run.command` (which should fail) with `network=none`
        - If exit_code == 0: task is INVALID (baseline passed unexpectedly)
        - If exit_code != 0: task is VALID (baseline fails as expected)
        - If setup fails: task is INVALID (setup_failed)
        - If timeout: task is INVALID (timeout)
        - Return `ValidationResult`
    """
    repo_dir = ensure_dir(workspace_dir / 'repo')
    valid = False
    error_details = None

    stdout_path, stderr_path, exit_code = clone_repo(
        url = task.repo.url,
        dest = repo_dir,
        logs_dir = logs_dir
    )

    error = check_exit_code(
        cmd_name = 'git_clone',
        exit_code = exit_code
    )

    if error is not None:
        raise error

    stdout_path, stderr_path, exit_code = checkout_commit(
        repo_dir = repo_dir,
        commit = task.repo.commit,
        logs_dir = logs_dir
    )

    error = check_exit_code(
        cmd_name = 'git_checkout',
        exit_code = exit_code
    )

    if error is not None:
        raise error

    sandbox = DockerSandbox(
        image = task.environment.docker_image,
        workdir = task.environment.workdir,
    )

    setup_commands = " && ".join(task.setup.commands)
    repo_relative_path = "repo"
    setup_commands = f"cd {repo_relative_path} && {setup_commands}"

    logger.info("Running setup commands")
    logger.debug("Setup commands: %s", setup_commands)

    setup_run_result = sandbox.run(
        workspace_host_path = workspace_dir,
        command = setup_commands,
        network = "bridge",
        timeout_sec = task.environment.timeout_sec,
        stdout_path = Path(logs_dir, "setup_stdout.txt"),
        stderr_path = Path(logs_dir, "setup_stderr.txt"),
    )

    error = check_exit_code(
        cmd_name = "Setup run",
        exit_code = setup_run_result.exit_code
    )
    
    if error is not None:
        if setup_run_result.exit_code == 124:
            error_details = "setup_timeout"
        else:
            error_details = "setup_failed"
        return ValidationResult(
            task_id = task.id,
            valid = valid,
            exit_code = setup_run_result.exit_code,
            stdout_path = setup_run_result.stdout_path,
            stderr_path = setup_run_result.stderr_path,
            error_reason = error_details,
            duration_sec = 0.0
        )


    logger.debug("Setup completed successfully")

    run_cmd = task.run.command
    run_cmd = f"cd repo && {run_cmd}"

    logger.info("Running task command")
    logger.debug("Run command: %s", run_cmd)

    start = time.perf_counter()

    run_run_result = sandbox.run(
        workspace_host_path = workspace_dir,
        command = run_cmd,
        network = "none",
        timeout_sec = task.environment.timeout_sec,
        stdout_path = Path(logs_dir, "run_stdout.txt"),
        stderr_path = Path(logs_dir, "run_stderr.txt"),
    )

    end = time.perf_counter()

    run_exit_code = run_run_result.exit_code

    match run_exit_code:
        case 0:
            error_details = "baseline_passed"
        case 1:
            valid = True
            error_details = None
        case 2:
            error_details = "execution_interruption_or_user_error"
        case 3:
            error_details = "internal_error"
        case 4:
            error_details = "cmd_line_error"
        case 5:
            error_details = "no_tests_collected"
        case 124:
            error_details = "timeout"
        case _:
            error_details = "unexpected_failure"

    return ValidationResult(
        task_id = task.id,
        valid = valid,
        exit_code = run_exit_code,
        stdout_path = run_run_result.stdout_path,
        stderr_path = run_run_result.stderr_path,
        error_reason = error_details,
        duration_sec = end - start
    )
    








    
    



    
    

    

    


