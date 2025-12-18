import logging
from datetime import datetime
from pathlib import Path

import ulid

from agentbench.sandbox.docker_sandbox import DockerSandbox
from agentbench.schemas.attempt_record import (
    AttemptRecord,
    BaselineValidationResult,
    TaskResult,
    TimestampInfo,
)
from agentbench.tasks.models import TaskSpec, ValidationResult
from agentbench.util.git import checkout_commit, clone_repo
from agentbench.util.jsonl import append_jsonl
from agentbench.util.paths import ensure_dir
from agentbench.util.process import check_exit_code

logger = logging.getLogger(__name__)


def validate_baseline(
    task: TaskSpec, workspace_dir: Path, logs_dir: Path
) -> ValidationResult:
    """
    Validate that a task's tests fail before any agent intervention.

    - Clone repo and checkout pinned commit
    - Run setup commands with `network=bridge`
    - Run `run.command` with `network=none`
    - exit_code == 0 -> INVALID (baseline passed unexpectedly)
    - exit_code != 0 -> VALID (baseline fails as expected)
    - Returns `ValidationResult`
    """

    """
    ### Integrate Attempt Recording
    - [ ] Update `validate_baseline()` to record attempts:
    - Generate ULID for each validation run
    - Record start/end timestamps
    - Write `AttemptRecord` to `attempts.jsonl` in the run directory
    """

    """
    - `BaselineValidationResult`: 
        `attempted: bool`, 
        `failed_as_expected: bool`, 
        `exit_code: int`

    - `TaskResult`: 
        `passed: bool`, 
        `exit_code: int`, 
        `failure_reason: str | None`
    """

    repo_dir = ensure_dir(workspace_dir / "repo")
    valid = False
    error_details = None
    started_at_dt = datetime.now()
    run_id = str(ulid.new())
    task_id = task.id
    suite = task.suite
    exit_code = None
    stdout_path = None
    stderr_path = None
    attempted = False

    try:
        stdout_path, stderr_path, exit_code = clone_repo(
            url=task.repo.url, dest=repo_dir, logs_dir=logs_dir
        )

        error = check_exit_code(cmd_name="git_clone", exit_code=exit_code)

        if error is not None:
            error_details = "git_clone_failed"
            raise error

        stdout_path, stderr_path, exit_code = checkout_commit(
            repo_dir=repo_dir, commit=task.repo.commit, logs_dir=logs_dir
        )

        error = check_exit_code(cmd_name="git_checkout", exit_code=exit_code)

        if error is not None:
            error_details = "git_checkout_failed"
            raise error

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

        exit_code = setup_run_result.exit_code
        stdout_path = setup_run_result.stdout_path
        stderr_path = setup_run_result.stderr_path

        error = check_exit_code(
            cmd_name="Setup run", exit_code=setup_run_result.exit_code
        )

        if error is not None:
            if setup_run_result.exit_code == 124:
                error_details = "setup_timeout"
            else:
                error_details = "setup_failed"
            raise error

        logger.debug("Setup completed successfully")

        run_cmd = task.run.command
        run_cmd = f"cd repo && {run_cmd}"

        logger.info("Running task command")
        logger.debug("Run command: %s", run_cmd)

        attempted = True

        run_run_result = sandbox.run(
            workspace_host_path=workspace_dir,
            command=run_cmd,
            network="none",
            timeout_sec=task.environment.timeout_sec,
            stdout_path=Path(logs_dir, "run_stdout.txt"),
            stderr_path=Path(logs_dir, "run_stderr.txt"),
        )

        exit_code = run_run_result.exit_code
        stdout_path = run_run_result.stdout_path
        stderr_path = run_run_result.stderr_path

        match exit_code:
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

    except Exception as e:
        logger.error("Validation failed: %s", str(e))

    finally:
        ended_at_dt = datetime.now()
        duration_sec = (ended_at_dt - started_at_dt).total_seconds()

        artifacts = {}
        if stdout_path is not None:
            artifacts["stdout"] = str(stdout_path)
        if stderr_path is not None:
            artifacts["stderr"] = str(stderr_path)
        artifacts["logs_dir"] = str(logs_dir)

        attempt_record = AttemptRecord(
            run_id=run_id,
            task_id=task_id,
            suite=suite,
            timestamps=TimestampInfo(
                started_at=started_at_dt, ended_at=ended_at_dt
            ),
            duration_sec=duration_sec,
            baseline_validation=BaselineValidationResult(
                attempted=attempted,
                failure_as_expected=valid,
                exit_code=exit_code if exit_code is not None else -1,
            ),
            result=TaskResult(
                passed=valid,
                exit_code=exit_code if exit_code is not None else -1,
                failure_reason=error_details,
            ),
            artifact_paths=artifacts,
        )
        attempts_file = logs_dir.parent / "attempts.jsonl"
        append_jsonl(attempts_file, attempt_record.model_dump(mode="json"))

    return ValidationResult(
        task_id=task.id,
        valid=valid,
        exit_code=exit_code if exit_code is not None else -1,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        error_reason=error_details,
        duration_sec=duration_sec,
    )
