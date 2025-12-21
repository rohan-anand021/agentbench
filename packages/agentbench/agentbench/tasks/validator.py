import logging
from pathlib import Path

from agentbench.sandbox.docker_sandbox import DockerSandbox
from agentbench.scoring import FailureReason
from agentbench.tasks.models import TaskSpec, ValidationResult
from agentbench.util.attempt import AttemptContext
from agentbench.util.git import checkout_commit, clone_repo
from agentbench.util.paths import ensure_dir

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
    stdout_path = None
    stderr_path = None

    with AttemptContext(
        task=task, logs_dir=logs_dir, variant="baseline"
    ) as attempt:
        try:
            # git clone
            attempt.mark_stage(stage="git_clone")

            stdout_path, stderr_path, exit_code = clone_repo(
                url=task.repo.url, dest=repo_dir, logs_dir=logs_dir
            )

            attempt.set_exit_code(exit_code)
            attempt.add_artifact("clone_stdout", str(stdout_path))
            attempt.add_artifact("clone_stderr", str(stderr_path))

            if exit_code != 0:
                attempt.set_failure_reason(
                    reason=FailureReason.GIT_CLONE_FAILED
                )
                raise RuntimeError(
                    f"git clone failed with exit code: {exit_code}"
                )

            # git checkout
            attempt.mark_stage(stage="git_checkout")

            stdout_path, stderr_path, exit_code = checkout_commit(
                repo_dir=repo_dir, commit=task.repo.commit, logs_dir=logs_dir
            )

            attempt.set_exit_code(exit_code)
            attempt.add_artifact("checkout_stdout", str(stdout_path))
            attempt.add_artifact("checkout_stderr", str(stderr_path))

            if exit_code != 0:
                attempt.set_failure_reason(
                    reason=FailureReason.GIT_CHECKOUT_FAILED
                )
                raise RuntimeError(
                    f"git checkout failed with exit code: {exit_code}"
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

            # setup run
            attempt.mark_stage(stage="setup_run")

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

            attempt.set_exit_code(exit_code)
            attempt.add_artifact("setup_stdout", str(stdout_path))
            attempt.add_artifact("setup_stderr", str(stderr_path))

            if exit_code != 0:
                if exit_code == 124:
                    attempt.set_failure_reason(
                        reason=FailureReason.SETUP_TIMEOUT
                    )
                else:
                    attempt.set_failure_reason(
                        reason=FailureReason.SETUP_FAILED
                    )
                raise RuntimeError(
                    f"setup run failed with exit code: {exit_code}"
                )

            logger.debug("Setup completed successfully")

            run_cmd = task.run.command
            run_cmd = f"cd repo && {run_cmd}"

            logger.info("Running task command")
            logger.debug("Run command: %s", run_cmd)

            # run
            attempt.mark_stage(stage="run")

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

            attempt.set_exit_code(exit_code)
            attempt.add_artifact("run_stdout", str(stdout_path))
            attempt.add_artifact("run_stderr", str(stderr_path))

            if exit_code == 0:
                attempt.set_failure_reason(
                    reason=FailureReason.BASELINE_NOT_FAILING
                )
                raise RuntimeError(
                    "baseline validation failed: tests passed unexpectedly"
                )
            elif exit_code in (124, 137):
                attempt.set_failure_reason(reason=FailureReason.TIMEOUT)
                raise RuntimeError(f"Run timed out with exit code: {exit_code}")
            else:
                attempt.valid = True

        except Exception as e:
            logger.error("Validation failed: %s", str(e))

    return ValidationResult(
        task_id=task.id,
        valid=attempt.valid,
        exit_code=attempt.exit_code if attempt.exit_code is not None else -1,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        error_reason=attempt.failure_reason,
        duration_sec=attempt.duration if attempt.duration is not None else 0.0,
    )
