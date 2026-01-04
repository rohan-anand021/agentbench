import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import ulid

from agentbench.agents.base import Agent
from agentbench.agents.llm_v0 import LLMAgentV0
from agentbench.agents.loop import AgentLoop
from agentbench.agents.types import AgentBudget, StopReason
from agentbench.agents.scripted import ScriptedAgent
from agentbench.llm.client import LLMClient
from agentbench.llm.config import LLMConfig
from agentbench.sandbox.docker_sandbox import DockerSandbox
from agentbench.schemas.attempt_record import (
    AttemptRecord,
    BaselineValidationResult,
    LimitsConfig,
    TaskResult,
    TimestampInfo,
)
from agentbench.scoring import FailureReason
from agentbench.tasks.models import TaskSpec
from agentbench.tasks.validator import validate_baseline
from agentbench.util.events import EventLogger
from agentbench.util.git import checkout_commit, clone_repo

logger = logging.getLogger(__name__)


def run_agent_attempt(
    task: TaskSpec,
    workspace_dir: Path,
    artifacts_dir: Path,
    llm_config: LLMConfig | None = None,
    llm_client: LLMClient | None = None,
    variant_override: str | None = None,
    log_llm_messages: bool | None = None,
    skip_baseline: bool = False,
    ) -> AttemptRecord:
    """
    Run an agent attempt on a task.
    
    Flow:
    1. Run baseline validation (tests should fail)
    2. Instantiate agent based on task.agent.entrypoint
    3. Call agent.run() with failing output
    4. Run final tests
    5. Record attempt
    """

    run_id = str(ulid.ULID())
    started_at = datetime.now(timezone.utc)
    logger.info("Starting agent attempt %s for task %s", run_id, task.id)
    
    result = None
    validation_result = None
    failure_reason = None
    exit_code = -1
    event_logger = None
    entrypoint = variant_override or task.agent.entrypoint

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

    def _failure_from_stop_reason(
        stop_reason: StopReason | None,
    ) -> FailureReason | None:
        if stop_reason is None:
            return None
        match stop_reason:
            case StopReason.SUCCESS:
                return None
            case StopReason.LLM_ERROR:
                return FailureReason.LLM_ERROR
            case StopReason.TOOL_ERROR:
                return FailureReason.TOOL_ERROR
            case StopReason.MAX_TIME:
                return FailureReason.TIMEOUT
            case StopReason.MAX_STEPS | StopReason.AGENT_GAVE_UP | StopReason.REPEATED_FAILURE:
                return FailureReason.AGENT_GAVE_UP
            case StopReason.INTERRUPTED:
                return FailureReason.INTERRUPTED
            case _:
                return None

    def get_agent(
        entrypoint: str,
        run_id: str,
        event_logger: EventLogger | None,
    ) -> Agent:
        if entrypoint == "scripted":
            return ScriptedAgent(run_id=run_id)
        elif entrypoint == "llm_v0":
            if not llm_config or not llm_client:
                raise ValueError("llm_v0 requires LLM config and client")
            return LLMAgentV0(
                config=llm_config,
                client=llm_client,
                event_logger=event_logger,
            )
        else:
            raise ValueError(f"Unknown agent entrypoint: {entrypoint}")

    try:
        logger.debug("Creating Docker sandbox with image %s", task.environment.docker_image)
        sandbox = DockerSandbox(
            image = task.environment.docker_image,
            workdir = task.environment.workdir
        )

        if skip_baseline:
            logger.info("Skipping baseline validation for task %s", task.id)
            logs_dir = artifacts_dir / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            repo_dir = workspace_dir / "repo"
            if repo_dir.exists():
                shutil.rmtree(repo_dir, ignore_errors=True)
            repo_url = _resolve_repo_url(task.repo.url, task.source_path)
            stdout_path, stderr_path, exit_code = clone_repo(
                url=repo_url,
                dest=repo_dir,
                logs_dir=logs_dir,
            )
            if exit_code != 0:
                failure_reason = FailureReason.GIT_CLONE_FAILED
                raise RuntimeError(
                    f"git clone failed with exit code: {exit_code}"
                )
            stdout_path, stderr_path, exit_code = checkout_commit(
                repo_dir=repo_dir,
                commit=task.repo.commit,
                logs_dir=logs_dir,
            )
            if exit_code != 0:
                failure_reason = FailureReason.GIT_CHECKOUT_FAILED
                raise RuntimeError(
                    f"git checkout failed with exit code: {exit_code}"
                )
        else:
            logger.debug("Running baseline validation")
            validation_result = validate_baseline(
                task = task,
                workspace_dir = workspace_dir,
                logs_dir = artifacts_dir / "logs"
            )

            if validation_result.exit_code == 0:
                logger.error("Baseline validation passed unexpectedly for task %s", task.id)
                raise ValueError(
                    "baseline validation passed unexpectedly - task is invalid"
                )

        if entrypoint != "scripted":
            event_logger = EventLogger(
                run_id=run_id,
                events_file=artifacts_dir / "events.jsonl",
                llm_messages_file=artifacts_dir / "llm_messages.jsonl",
                log_llm_messages=log_llm_messages,
            )

        logger.debug("Instantiating agent with entrypoint %s", entrypoint)
        agent = get_agent(
            entrypoint = entrypoint,
            run_id = run_id,
            event_logger = event_logger,
        )

        if isinstance(agent, ScriptedAgent):
            failing_output = ""
            if validation_result and validation_result.stderr_path:
                failing_output = validation_result.stderr_path.read_text()
            result = agent.run(
                task = task,
                sandbox = sandbox,
                workspace_root = workspace_dir,
                artifacts_dir = artifacts_dir,
                failing_output = failing_output,
            )
        else:
            # Use AgentLoop for other agents (like llm_v0)
            if event_logger is None:
                event_logger = EventLogger(
                    run_id=run_id,
                    events_file=artifacts_dir / "events.jsonl",
                    llm_messages_file=artifacts_dir / "llm_messages.jsonl",
                    log_llm_messages=log_llm_messages,
                )
            budget = None
            if task.agent is not None:
                budget = AgentBudget(
                    max_steps=task.agent.max_steps,
                    max_time_sec=max(task.environment.timeout_sec, 180),
                )
            loop = AgentLoop(
                agent=agent,
                task=task,
                workspace_root=workspace_dir,
                artifacts_dir=artifacts_dir,
                sandbox=sandbox,
                event_logger=event_logger,
                budget=budget,
            )
            result = loop.run()

        exit_code = result.final_test_exit_code if result else -1

    except KeyboardInterrupt:
        logger.warning("Agent attempt %s interrupted by user", run_id)
        failure_reason = FailureReason.INTERRUPTED
    except Exception as e:
        logger.exception("Agent attempt %s failed with error: %s", run_id, e)
        failure_reason = FailureReason.UNKNOWN

    stop_reason = result.stop_reason if result else None
    failure_from_stop = _failure_from_stop_reason(stop_reason)
    if failure_reason is None:
        failure_reason = failure_from_stop
    if (
        failure_reason is None
        and result
        and not result.success
        and exit_code is not None
    ):
        failure_reason = FailureReason.from_pytest_exit_code(exit_code)

    if event_logger and result:
        event_logger.log_agent_finished(
            success=result.success,
            stop_reason=str(result.stop_reason),
            steps_taken=result.steps_taken,
            final_test_exit_code=result.final_test_exit_code,
            final_test_passed=result.final_test_passed,
            failure_reason=str(failure_reason) if failure_reason else None,
        )

    ended_at = datetime.now(timezone.utc)
    duration = (ended_at - started_at).total_seconds()
    logger.info("Agent attempt %s completed in %.2fs, passed=%s", run_id, duration, result.success if result else False)

    return AttemptRecord(
        run_id = run_id,
        task_id = task.id,
        suite = task.suite,
        task_spec_version = task.task_spec_version,
        harness_min_version = task.harness_min_version,
        labels = task.labels,
        timestamps = TimestampInfo(
            started_at = started_at,
            ended_at = ended_at
        ),
        duration_sec = (ended_at - started_at).total_seconds(),
        baseline_validation = BaselineValidationResult(
            attempted = validation_result is not None,
            failed_as_expected = validation_result.exit_code != 0 if validation_result else False,
            exit_code = validation_result.exit_code if validation_result else -1
        ),
        result = TaskResult(
            passed = result.success if result else False,
            exit_code = exit_code if exit_code is not None else -1,
            failure_reason = failure_reason,
            stop_reason = stop_reason,
        ),
        artifact_paths = {
            "patch_files": ",".join(result.patches_applied) if result else ""
        },
        variant = entrypoint,
        model = None,
        limits = LimitsConfig(
            timeout_sec = task.environment.timeout_sec,
            tool_timeout_sec = None
        ),
        schema_version = "0.1.0"
    )





    


    

    
