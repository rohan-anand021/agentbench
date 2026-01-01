import logging
from datetime import datetime
from pathlib import Path

import ulid

from agentbench.agents.base import Agent
from agentbench.agents.scripted import ScriptedAgent
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

logger = logging.getLogger(__name__)


def run_agent_attempt(
    task: TaskSpec,
    workspace_dir: Path,
    artifacts_dir: Path
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
    started_at = datetime.now()
    logger.info("Starting agent attempt %s for task %s", run_id, task.id)
    
    result = None
    validation_result = None
    failure_reason = None
    exit_code = -1

    def get_agent(
        entrypoint: str,
        run_id: str
    ) -> Agent:
        agents = {
            "scripted": ScriptedAgent
        }

        if entrypoint not in agents:
            raise ValueError(
                f"Unknown agent entrypoint: {entrypoint}"
            )
        
        return agents[entrypoint](run_id = run_id)

    try:
        logger.debug("Creating Docker sandbox with image %s", task.environment.docker_image)
        sandbox = DockerSandbox(
            image = task.environment.docker_image,
            workdir = task.environment.workdir
        )

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

        logger.debug("Instantiating agent with entrypoint %s", task.agent.entrypoint)
        agent = get_agent(
            entrypoint = task.agent.entrypoint,
            run_id = run_id
        )

        result = agent.run(
            task = task,
            sandbox = sandbox,
            workspace_root = workspace_dir,
            artifacts_dir = artifacts_dir,
            failing_output = validation_result.stderr_path.read_text() if validation_result.stderr_path else ""
        )

        exit_code = result.exit_code

    except KeyboardInterrupt:
        logger.warning("Agent attempt %s interrupted by user", run_id)
        failure_reason = FailureReason.INTERRUPTED
    except Exception as e:
        logger.exception("Agent attempt %s failed with error: %s", run_id, e)
        failure_reason = FailureReason.UNKNOWN

    ended_at = datetime.now()
    duration = (ended_at - started_at).total_seconds()
    logger.info("Agent attempt %s completed in %.2fs, passed=%s", run_id, duration, result.success if result else False)

    return AttemptRecord(
        run_id = run_id,
        task_id = task.id,
        suite = task.suite,
        timestamps = TimestampInfo(
            started_at = started_at,
            ended_at = ended_at
        ),
        duration_sec = (ended_at - started_at).total_seconds(),
        baseline_validation = BaselineValidationResult(
            attempted = validation_result is not None,
            failure_as_expected = validation_result.exit_code != 0 if validation_result else False,
            exit_code = validation_result.exit_code if validation_result else -1
        ),
        result = TaskResult(
            passed = result.success if result else False,
            exit_code = exit_code,
            failure_reason = failure_reason or (FailureReason.from_pytest_exit_code(exit_code) if result and not result.success else None)
        ),
        artifact_paths = {
            "patch_files": ",".join(result.patch_files) if result else ""
        },
        variant = "baseline",
        model = None,
        limits = LimitsConfig(
            timeout_sec = task.environment.timeout_sec,
            tool_timeout_sec = None
        ),
        schema_version = "0.1.0"
    )





    


    

    

