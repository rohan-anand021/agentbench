from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from agentbench.tasks.loader import load_task
from agentbench.tasks.models import (
    EnvironmentSpec,
    RepoSpec,
    RunSpec,
    SetupSpec,
    TaskSpec,
    ValidationResult,
)
from agentbench.tasks.validator import validate_baseline

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_task_spec() -> TaskSpec:
    """Creates a mock TaskSpec for unit testing."""
    return TaskSpec(
        id="test_task",
        suite="test-suite",
        repo=RepoSpec(url="https://github.com/example/repo", commit="abc123"),
        environment=EnvironmentSpec(
            docker_image="test-image:latest",
            workdir="/workspace",
            timeout_sec=300,
        ),
        setup=SetupSpec(commands=["pip install ."]),
        run=RunSpec(command="pytest -q"),
        source_path=Path("/tmp/test/task.yaml"),
    )


@pytest.fixture
def toy_fail_pytest_task() -> TaskSpec:
    """Loads the real toy_fail_pytest task."""
    task_yaml = (
        Path(__file__).parent.parent.parent.parent
        / "tasks"
        / "custom-dev"
        / "toy_fail_pytest"
        / "task.yaml"
    )
    return load_task(task_yaml)


# =============================================================================
# Integration Tests (require Docker)
# =============================================================================


@pytest.mark.integration
@pytest.mark.docker
def test_validate_baseline_toy_fail_pytest_is_valid(
    toy_fail_pytest_task: TaskSpec, tmp_path: Path
):
    """
    Integration test: validate_baseline() correctly identifies toy_fail_pytest as valid.

    The toy_fail_pytest task has a bug (add returns a-b instead of a+b),
    so the tests should fail, making the baseline valid.

    Requires Docker to be running.
    """
    workspace_dir = tmp_path / "workspace"
    logs_dir = tmp_path / "logs"
    workspace_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)

    result = validate_baseline(
        task=toy_fail_pytest_task,
        workspace_dir=workspace_dir,
        logs_dir=logs_dir,
    )

    assert isinstance(result, ValidationResult)
    assert result.task_id == "toy_fail_pytest"
    assert result.valid is True, (
        f"Expected valid=True but got valid={result.valid}, error_reason={result.error_reason}"
    )
    assert result.exit_code == 1  # pytest returns 1 when tests fail
    assert result.error_reason is None
    assert result.duration_sec > 0


@pytest.mark.integration
@pytest.mark.docker
def test_validate_baseline_setup_failures_are_caught(tmp_path: Path):
    """
    Integration test: validate_baseline() catches and reports setup failures.

    Creates a task with a broken setup command.
    """
    # Create a minimal task spec with a failing setup command
    task = TaskSpec(
        id="broken_setup_task",
        suite="test-suite",
        repo=RepoSpec(
            url=str(
                Path(__file__).parent.parent.parent.parent
                / "examples"
                / "toy_repo"
            ),
            commit="HEAD",
        ),
        environment=EnvironmentSpec(
            docker_image="ghcr.io/agentbench/py-runner:0.1.0",
            workdir="/workspace",
            timeout_sec=60,
        ),
        setup=SetupSpec(commands=["pip install nonexistent-package-xyz-12345"]),
        run=RunSpec(command="pytest -q"),
        source_path=Path("/tmp/test/task.yaml"),
    )

    workspace_dir = tmp_path / "workspace"
    logs_dir = tmp_path / "logs"
    workspace_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)

    result = validate_baseline(
        task=task, workspace_dir=workspace_dir, logs_dir=logs_dir
    )

    assert isinstance(result, ValidationResult)
    assert result.valid is False
    assert result.error_reason == "setup_failed"


# =============================================================================
# Unit Tests (with mocked dependencies)
# =============================================================================


@patch("agentbench.tasks.validator.DockerSandbox")
@patch("agentbench.tasks.validator.checkout_commit")
@patch("agentbench.tasks.validator.clone_repo")
def test_validate_baseline_returns_valid_when_tests_fail(
    mock_clone_repo,
    mock_checkout_commit,
    mock_docker_sandbox,
    mock_task_spec: TaskSpec,
    tmp_path: Path,
):
    """Unit test: Returns valid=True when run command exits with code 1 (tests failed)."""
    # Setup mocks
    mock_clone_repo.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )
    mock_checkout_commit.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )

    # Create mock files
    (tmp_path / "stdout.txt").touch()
    (tmp_path / "stderr.txt").touch()

    mock_sandbox_instance = MagicMock()
    mock_docker_sandbox.return_value = mock_sandbox_instance

    # Setup run returns success (exit 0), Run returns failure (exit 1)
    setup_result = Mock(
        exit_code=0,
        stdout_path=tmp_path / "setup_stdout.txt",
        stderr_path=tmp_path / "setup_stderr.txt",
    )
    run_result = Mock(
        exit_code=1,
        stdout_path=tmp_path / "run_stdout.txt",
        stderr_path=tmp_path / "run_stderr.txt",
    )
    mock_sandbox_instance.run.side_effect = [setup_result, run_result]

    workspace_dir = tmp_path / "workspace"
    logs_dir = tmp_path / "logs"

    result = validate_baseline(
        task=mock_task_spec, workspace_dir=workspace_dir, logs_dir=logs_dir
    )

    assert result.valid is True
    assert result.exit_code == 1
    assert result.error_reason is None


@patch("agentbench.tasks.validator.DockerSandbox")
@patch("agentbench.tasks.validator.checkout_commit")
@patch("agentbench.tasks.validator.clone_repo")
def test_validate_baseline_returns_invalid_when_tests_pass(
    mock_clone_repo,
    mock_checkout_commit,
    mock_docker_sandbox,
    mock_task_spec: TaskSpec,
    tmp_path: Path,
):
    """Unit test: Returns valid=False when run command exits with code 0 (tests passed)."""
    # Setup mocks
    mock_clone_repo.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )
    mock_checkout_commit.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )

    (tmp_path / "stdout.txt").touch()
    (tmp_path / "stderr.txt").touch()

    mock_sandbox_instance = MagicMock()
    mock_docker_sandbox.return_value = mock_sandbox_instance

    setup_result = Mock(
        exit_code=0,
        stdout_path=tmp_path / "setup_stdout.txt",
        stderr_path=tmp_path / "setup_stderr.txt",
    )
    run_result = Mock(
        exit_code=0,
        stdout_path=tmp_path / "run_stdout.txt",
        stderr_path=tmp_path / "run_stderr.txt",
    )
    mock_sandbox_instance.run.side_effect = [setup_result, run_result]

    workspace_dir = tmp_path / "workspace"
    logs_dir = tmp_path / "logs"

    result = validate_baseline(
        task=mock_task_spec, workspace_dir=workspace_dir, logs_dir=logs_dir
    )

    assert result.valid is False
    assert result.exit_code == 0
    assert result.error_reason == "baseline_passed"


@patch("agentbench.tasks.validator.DockerSandbox")
@patch("agentbench.tasks.validator.checkout_commit")
@patch("agentbench.tasks.validator.clone_repo")
def test_validate_baseline_returns_invalid_on_setup_failure(
    mock_clone_repo,
    mock_checkout_commit,
    mock_docker_sandbox,
    mock_task_spec: TaskSpec,
    tmp_path: Path,
):
    """Unit test: Returns valid=False with error_reason='setup_failed' when setup fails."""
    # Setup mocks
    mock_clone_repo.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )
    mock_checkout_commit.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )

    (tmp_path / "stdout.txt").touch()
    (tmp_path / "stderr.txt").touch()

    mock_sandbox_instance = MagicMock()
    mock_docker_sandbox.return_value = mock_sandbox_instance

    # Setup fails with exit code 1
    setup_result = Mock(
        exit_code=1,
        stdout_path=tmp_path / "setup_stdout.txt",
        stderr_path=tmp_path / "setup_stderr.txt",
    )
    mock_sandbox_instance.run.return_value = setup_result

    workspace_dir = tmp_path / "workspace"
    logs_dir = tmp_path / "logs"

    result = validate_baseline(
        task=mock_task_spec, workspace_dir=workspace_dir, logs_dir=logs_dir
    )

    assert result.valid is False
    assert result.error_reason == "setup_failed"


@patch("agentbench.tasks.validator.DockerSandbox")
@patch("agentbench.tasks.validator.checkout_commit")
@patch("agentbench.tasks.validator.clone_repo")
def test_validate_baseline_returns_invalid_on_setup_timeout(
    mock_clone_repo,
    mock_checkout_commit,
    mock_docker_sandbox,
    mock_task_spec: TaskSpec,
    tmp_path: Path,
):
    """Unit test: Returns valid=False with error_reason='setup_timeout' when setup times out."""
    # Setup mocks
    mock_clone_repo.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )
    mock_checkout_commit.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )

    (tmp_path / "stdout.txt").touch()
    (tmp_path / "stderr.txt").touch()

    mock_sandbox_instance = MagicMock()
    mock_docker_sandbox.return_value = mock_sandbox_instance

    # Setup times out (exit code 124)
    setup_result = Mock(
        exit_code=124,
        stdout_path=tmp_path / "setup_stdout.txt",
        stderr_path=tmp_path / "setup_stderr.txt",
    )
    mock_sandbox_instance.run.return_value = setup_result

    workspace_dir = tmp_path / "workspace"
    logs_dir = tmp_path / "logs"

    result = validate_baseline(
        task=mock_task_spec, workspace_dir=workspace_dir, logs_dir=logs_dir
    )

    assert result.valid is False
    assert result.error_reason == "setup_timeout"


@patch("agentbench.tasks.validator.DockerSandbox")
@patch("agentbench.tasks.validator.checkout_commit")
@patch("agentbench.tasks.validator.clone_repo")
def test_validate_baseline_returns_invalid_on_run_timeout(
    mock_clone_repo,
    mock_checkout_commit,
    mock_docker_sandbox,
    mock_task_spec: TaskSpec,
    tmp_path: Path,
):
    """Unit test: Returns valid=False with error_reason='timeout' when run times out."""
    # Setup mocks
    mock_clone_repo.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )
    mock_checkout_commit.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )

    (tmp_path / "stdout.txt").touch()
    (tmp_path / "stderr.txt").touch()

    mock_sandbox_instance = MagicMock()
    mock_docker_sandbox.return_value = mock_sandbox_instance

    setup_result = Mock(
        exit_code=0,
        stdout_path=tmp_path / "setup_stdout.txt",
        stderr_path=tmp_path / "setup_stderr.txt",
    )
    run_result = Mock(
        exit_code=124,
        stdout_path=tmp_path / "run_stdout.txt",
        stderr_path=tmp_path / "run_stderr.txt",
    )
    mock_sandbox_instance.run.side_effect = [setup_result, run_result]

    workspace_dir = tmp_path / "workspace"
    logs_dir = tmp_path / "logs"

    result = validate_baseline(
        task=mock_task_spec, workspace_dir=workspace_dir, logs_dir=logs_dir
    )

    assert result.valid is False
    assert result.exit_code == 124
    assert result.error_reason == "timeout"


@patch("agentbench.tasks.validator.DockerSandbox")
@patch("agentbench.tasks.validator.checkout_commit")
@patch("agentbench.tasks.validator.clone_repo")
def test_validate_baseline_handles_no_tests_collected(
    mock_clone_repo,
    mock_checkout_commit,
    mock_docker_sandbox,
    mock_task_spec: TaskSpec,
    tmp_path: Path,
):
    """Unit test: Returns valid=False with error_reason='no_tests_collected' for exit code 5."""
    # Setup mocks
    mock_clone_repo.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )
    mock_checkout_commit.return_value = (
        tmp_path / "stdout.txt",
        tmp_path / "stderr.txt",
        0,
    )

    (tmp_path / "stdout.txt").touch()
    (tmp_path / "stderr.txt").touch()

    mock_sandbox_instance = MagicMock()
    mock_docker_sandbox.return_value = mock_sandbox_instance

    setup_result = Mock(
        exit_code=0,
        stdout_path=tmp_path / "setup_stdout.txt",
        stderr_path=tmp_path / "setup_stderr.txt",
    )
    run_result = Mock(
        exit_code=5,
        stdout_path=tmp_path / "run_stdout.txt",
        stderr_path=tmp_path / "run_stderr.txt",
    )
    mock_sandbox_instance.run.side_effect = [setup_result, run_result]

    workspace_dir = tmp_path / "workspace"
    logs_dir = tmp_path / "logs"

    result = validate_baseline(
        task=mock_task_spec, workspace_dir=workspace_dir, logs_dir=logs_dir
    )

    assert result.valid is False
    assert result.exit_code == 5
    assert result.error_reason == "no_tests_collected"
