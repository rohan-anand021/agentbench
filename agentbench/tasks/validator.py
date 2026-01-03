import hashlib
import logging
import re
import time
from pathlib import Path

from agentbench.sandbox.docker_sandbox import DockerSandbox
from agentbench.scoring import FailureReason
from agentbench.tasks.models import TaskSpec, ValidationResult, ValidationSpec
from agentbench.util.attempt import AttemptContext
from agentbench.util.git import (
    checkout_commit,
    clone_repo,
    diff_patch,
    diff_stat,
    status_porcelain,
)
from agentbench.util.paths import ensure_dir

logger = logging.getLogger(__name__)


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


def _read_log(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _failure_signature(stdout: str, stderr: str) -> str:
    combined = "\n".join([stdout, stderr]).strip()
    nodeids = []
    for line in combined.splitlines():
        match = re.match(r"^(FAILED|ERROR)\s+(.+?)(?:\s+-\s+.*)?$", line)
        if match:
            nodeids.append(f"{match.group(1)} {match.group(2).strip()}")

    if nodeids:
        return "nodeids:" + "|".join(sorted(set(nodeids)))

    if not combined:
        return "empty-output"

    digest = hashlib.sha256(combined.encode("utf-8", errors="replace")).hexdigest()
    return f"sha256:{digest}"


def _evaluate_expectations(
    validation: ValidationSpec,
    exit_code: int,
    stdout: str,
    stderr: str,
) -> list[str]:
    mismatches: list[str] = []
    combined = "\n".join([stdout, stderr])

    if validation.expected_exit_codes:
        if exit_code not in validation.expected_exit_codes:
            mismatches.append(
                f"exit_code {exit_code} not in expected_exit_codes {validation.expected_exit_codes}"
            )

    if validation.expected_failure_regex:
        if not re.search(validation.expected_failure_regex, combined, re.MULTILINE):
            mismatches.append(
                f"expected_failure_regex did not match: {validation.expected_failure_regex}"
            )

    if validation.expected_stdout_regex:
        if not re.search(validation.expected_stdout_regex, stdout, re.MULTILINE):
            mismatches.append(
                f"expected_stdout_regex did not match: {validation.expected_stdout_regex}"
            )

    if validation.expected_stderr_regex:
        if not re.search(validation.expected_stderr_regex, stderr, re.MULTILINE):
            mismatches.append(
                f"expected_stderr_regex did not match: {validation.expected_stderr_regex}"
            )

    if validation.disallowed_failure_regex:
        for pattern in validation.disallowed_failure_regex:
            if re.search(pattern, combined, re.MULTILINE):
                mismatches.append(
                    f"disallowed_failure_regex matched: {pattern}"
                )

    if validation.expected_failing_tests:
        for expected_test in validation.expected_failing_tests:
            if expected_test not in combined:
                mismatches.append(
                    f"expected_failing_tests missing: {expected_test}"
                )

    return mismatches


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

    logs_dir = ensure_dir(logs_dir)
    repo_dir = ensure_dir(workspace_dir / "repo")
    stdout_path = None
    stderr_path = None
    start_time = time.monotonic()

    with AttemptContext(
        task=task, logs_dir=logs_dir, variant="baseline"
    ) as attempt:
        try:
            # git clone
            attempt.mark_stage(stage="git_clone")

            repo_url = _resolve_repo_url(task.repo.url, task.source_path)
            if repo_url != task.repo.url:
                logger.info(
                    "Resolved repo URL from %s to %s",
                    task.repo.url,
                    repo_url,
                )

            stdout_path, stderr_path, exit_code = clone_repo(
                url=repo_url, dest=repo_dir, logs_dir=logs_dir
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

            logger.info("Running setup commands")
            logger.debug("Setup commands: %s", setup_commands)

            # setup run
            attempt.mark_stage(stage="setup")
            setup_stdout_path = Path(logs_dir, "setup_stdout.txt")
            setup_stderr_path = Path(logs_dir, "setup_stderr.txt")
            if setup_commands.strip():
                setup_commands = (
                    f"cd {repo_relative_path} && {setup_commands}"
                )
                setup_run_result = sandbox.run(
                    workspace_host_path=workspace_dir,
                    command=setup_commands,
                    network="bridge",
                    timeout_sec=task.environment.timeout_sec,
                    stdout_path=setup_stdout_path,
                    stderr_path=setup_stderr_path,
                )

                exit_code = setup_run_result.exit_code
                stdout_path = setup_run_result.stdout_path
                stderr_path = setup_run_result.stderr_path
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
                exit_code = 0
                stdout_path = setup_stdout_path
                stderr_path = setup_stderr_path

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

            status_stdout, status_stderr, status_exit = status_porcelain(
                repo_dir=repo_dir,
                logs_dir=logs_dir,
            )
            attempt.add_artifact("post_setup_status_stdout", str(status_stdout))
            attempt.add_artifact("post_setup_status_stderr", str(status_stderr))

            diff_stat_stdout, diff_stat_stderr, diff_stat_exit = diff_stat(
                repo_dir=repo_dir,
                logs_dir=logs_dir,
            )
            attempt.add_artifact("post_setup_diff_stat_stdout", str(diff_stat_stdout))
            attempt.add_artifact("post_setup_diff_stat_stderr", str(diff_stat_stderr))

            diff_stdout, diff_stderr, diff_exit = diff_patch(
                repo_dir=repo_dir,
                logs_dir=logs_dir,
            )
            attempt.add_artifact("post_setup_diff_stdout", str(diff_stdout))
            attempt.add_artifact("post_setup_diff_stderr", str(diff_stderr))

            if status_exit != 0 or diff_stat_exit != 0 or diff_exit != 0:
                attempt.set_exit_code(
                    status_exit
                    if status_exit != 0
                    else diff_stat_exit
                    if diff_stat_exit != 0
                    else diff_exit
                )
                attempt.set_failure_reason(reason=FailureReason.UNKNOWN)
                raise RuntimeError("post-setup git inspection failed")

            status_output = _read_log(status_stdout).strip()
            if status_output:
                attempt.set_failure_reason(
                    reason=FailureReason.SETUP_DIRTY_WORKTREE
                )
                raise RuntimeError(
                    "setup modified tracked files; baseline invalid"
                )

            run_cmd = task.run.command
            run_cmd = f"cd repo && {run_cmd}"

            logger.info("Running task command")
            logger.debug("Run command: %s", run_cmd)

            # run
            attempt.mark_stage(stage="baseline_run")

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

            failure_reason = FailureReason.from_pytest_exit_code(exit_code)
            if failure_reason is not None and failure_reason != FailureReason.TESTS_FAILED:
                attempt.set_failure_reason(reason=failure_reason)
                raise RuntimeError(
                    f"baseline validation failed with exit code {exit_code}"
                )

            validation = task.validation
            stdout_text = _read_log(stdout_path)
            stderr_text = _read_log(stderr_path)
            if validation:
                mismatches = _evaluate_expectations(
                    validation=validation,
                    exit_code=exit_code,
                    stdout=stdout_text,
                    stderr=stderr_text,
                )
                if mismatches:
                    mismatch_path = logs_dir / "baseline_expectation_mismatch.txt"
                    mismatch_path.write_text(
                        "\n".join(mismatches),
                        encoding="utf-8",
                        newline="\n",
                    )
                    attempt.add_artifact(
                        "baseline_expectation_mismatch", str(mismatch_path)
                    )
                    attempt.set_failure_reason(
                        reason=FailureReason.BASELINE_MISMATCH
                    )
                    raise RuntimeError(
                        "baseline output did not match expected failure hints"
                    )

            signature = _failure_signature(stdout_text, stderr_text)
            signature_path = logs_dir / "baseline_failure_signature.txt"
            signature_path.write_text(
                signature, encoding="utf-8", newline="\n"
            )
            attempt.add_artifact(
                "baseline_failure_signature", str(signature_path)
            )

            attempt.mark_stage(stage="baseline_rerun")
            elapsed = time.monotonic() - start_time
            remaining = task.environment.timeout_sec - elapsed
            min_rerun_budget = 5

            if remaining < min_rerun_budget:
                skip_path = logs_dir / "baseline_rerun_skipped.txt"
                skip_path.write_text(
                    (
                        "Baseline rerun skipped due to low remaining time.\n"
                        f"elapsed_sec={elapsed:.2f}\n"
                        f"remaining_sec={max(0.0, remaining):.2f}\n"
                    ),
                    encoding="utf-8",
                    newline="\n",
                )
                attempt.add_artifact(
                    "baseline_rerun_skipped", str(skip_path)
                )
            else:
                rerun_timeout = max(1, int(remaining))
                rerun_stdout = Path(logs_dir, "run_rerun_stdout.txt")
                rerun_stderr = Path(logs_dir, "run_rerun_stderr.txt")
                rerun_result = sandbox.run(
                    workspace_host_path=workspace_dir,
                    command=run_cmd,
                    network="none",
                    timeout_sec=rerun_timeout,
                    stdout_path=rerun_stdout,
                    stderr_path=rerun_stderr,
                )

                attempt.add_artifact("run_rerun_stdout", str(rerun_stdout))
                attempt.add_artifact("run_rerun_stderr", str(rerun_stderr))

                rerun_stdout_text = _read_log(rerun_stdout)
                rerun_stderr_text = _read_log(rerun_stderr)
                rerun_signature = _failure_signature(
                    rerun_stdout_text, rerun_stderr_text
                )
                rerun_signature_path = logs_dir / "baseline_rerun_signature.txt"
                rerun_signature_path.write_text(
                    rerun_signature, encoding="utf-8", newline="\n"
                )
                attempt.add_artifact(
                    "baseline_rerun_signature", str(rerun_signature_path)
                )

                comparison_path = logs_dir / "baseline_rerun_comparison.txt"
                comparison_path.write_text(
                    "\n".join(
                        [
                            f"run_1_exit_code: {exit_code}",
                            f"run_1_signature: {signature}",
                            f"run_2_exit_code: {rerun_result.exit_code}",
                            f"run_2_signature: {rerun_signature}",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                attempt.add_artifact(
                    "baseline_rerun_comparison", str(comparison_path)
                )

                if (
                    rerun_result.exit_code != exit_code
                    or rerun_signature != signature
                ):
                    attempt.set_exit_code(rerun_result.exit_code)
                    attempt.set_failure_reason(
                        reason=FailureReason.BASELINE_FLAKY
                    )
                    raise RuntimeError(
                        "baseline validation failed: flaky baseline"
                    )

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
