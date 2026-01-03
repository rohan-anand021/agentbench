"""Unit tests for Task Pydantic models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentbench.tasks.models import (
    EnvironmentSpec,
    RepoSpec,
    RunSpec,
    SetupSpec,
    TaskSpec,
    ValidationResult,
)


class TestRepoSpec:
    """Tests for RepoSpec model."""

    def test_repo_spec_creation(self):
        """RepoSpec can be created with url and commit."""
        repo = RepoSpec(url="https://github.com/example/repo.git", commit="abc123")
        assert repo.url == "https://github.com/example/repo.git"
        assert repo.commit == "abc123"

    def test_repo_spec_requires_url(self):
        """RepoSpec requires url field."""
        with pytest.raises(ValidationError):
            RepoSpec(commit="abc123")

    def test_repo_spec_requires_commit(self):
        """RepoSpec requires commit field."""
        with pytest.raises(ValidationError):
            RepoSpec(url="https://github.com/example/repo.git")

    def test_repo_spec_serialization(self):
        """RepoSpec serializes to JSON correctly."""
        repo = RepoSpec(url="https://github.com/example/repo.git", commit="abc123")
        json_data = json.loads(repo.model_dump_json())

        assert json_data["url"] == "https://github.com/example/repo.git"
        assert json_data["commit"] == "abc123"


class TestEnvironmentSpec:
    """Tests for EnvironmentSpec model."""

    def test_environment_spec_creation(self):
        """EnvironmentSpec can be created with all fields."""
        env = EnvironmentSpec(
            docker_image="python:3.11",
            workdir="/workspace",
            timeout_sec=300,
        )
        assert env.docker_image == "python:3.11"
        assert env.workdir == "/workspace"
        assert env.timeout_sec == 300

    def test_environment_spec_requires_docker_image(self):
        """EnvironmentSpec requires docker_image field."""
        with pytest.raises(ValidationError):
            EnvironmentSpec(workdir="/workspace", timeout_sec=300)

    def test_environment_spec_requires_workdir(self):
        """EnvironmentSpec requires workdir field."""
        with pytest.raises(ValidationError):
            EnvironmentSpec(docker_image="python:3.11", timeout_sec=300)

    def test_environment_spec_requires_timeout(self):
        """EnvironmentSpec requires timeout_sec field."""
        with pytest.raises(ValidationError):
            EnvironmentSpec(docker_image="python:3.11", workdir="/workspace")

    def test_environment_spec_timeout_must_be_int(self):
        """EnvironmentSpec timeout_sec must be coercible to integer."""
        # Pydantic v2 coerces "300" to 300, but lists fail
        with pytest.raises(ValidationError):
            EnvironmentSpec(
                docker_image="python:3.11",
                workdir="/workspace",
                timeout_sec=[300],  # List instead of int
            )


class TestSetupSpec:
    """Tests for SetupSpec model."""

    def test_setup_spec_with_commands(self):
        """SetupSpec can be created with commands list."""
        setup = SetupSpec(commands=["pip install -e .", "npm install"])
        assert len(setup.commands) == 2
        assert setup.commands[0] == "pip install -e ."

    def test_setup_spec_empty_commands(self):
        """SetupSpec can have empty commands list."""
        setup = SetupSpec(commands=[])
        assert setup.commands == []

    def test_setup_spec_requires_commands(self):
        """SetupSpec requires commands field."""
        with pytest.raises(ValidationError):
            SetupSpec()


class TestRunSpec:
    """Tests for RunSpec model."""

    def test_run_spec_creation(self):
        """RunSpec can be created with command."""
        run = RunSpec(command="pytest tests/")
        assert run.command == "pytest tests/"

    def test_run_spec_requires_command(self):
        """RunSpec requires command field."""
        with pytest.raises(ValidationError):
            RunSpec()


class TestTaskSpec:
    """Tests for TaskSpec model."""

    def make_valid_task_spec(self, **overrides) -> TaskSpec:
        """Helper to create a valid TaskSpec with optional overrides."""
        defaults = {
            "task_spec_version": "1.0",
            "id": "test-task-1",
            "suite": "test-suite",
            "repo": RepoSpec(
                url="https://github.com/example/repo.git",
                commit="abc123",
            ),
            "environment": EnvironmentSpec(
                docker_image="python:3.11",
                workdir="/workspace",
                timeout_sec=300,
            ),
            "setup": SetupSpec(commands=["pip install -e ."]),
            "run": RunSpec(command="pytest tests/"),
            "validation": None,
            "harness_min_version": "0.1.0",
            "labels": ["smoke"],
            "source_path": Path("/tasks/test-suite/test-task-1/task.yaml"),
        }
        defaults.update(overrides)
        return TaskSpec(**defaults)

    def test_task_spec_creation(self):
        """TaskSpec can be created with all fields."""
        task = self.make_valid_task_spec()
        assert task.id == "test-task-1"
        assert task.suite == "test-suite"
        assert task.repo.url == "https://github.com/example/repo.git"
        assert task.environment.docker_image == "python:3.11"
        assert len(task.setup.commands) == 1
        assert task.run.command == "pytest tests/"
        assert task.task_spec_version == "1.0"
        assert task.harness_min_version == "0.1.0"
        assert task.labels == ["smoke"]

    def test_task_spec_requires_id(self):
        """TaskSpec requires id field."""
        with pytest.raises(ValidationError):
            TaskSpec(
                task_spec_version="1.0",
                suite="test-suite",
                repo=RepoSpec(url="https://example.com", commit="abc"),
                environment=EnvironmentSpec(
                    docker_image="python:3.11", workdir="/w", timeout_sec=300
                ),
                setup=SetupSpec(commands=[]),
                run=RunSpec(command="test"),
                validation=None,
                harness_min_version=None,
                labels=None,
                source_path=Path("/path"),
            )

    def test_task_spec_requires_suite(self):
        """TaskSpec requires suite field."""
        with pytest.raises(ValidationError):
            TaskSpec(
                task_spec_version="1.0",
                id="test-1",
                repo=RepoSpec(url="https://example.com", commit="abc"),
                environment=EnvironmentSpec(
                    docker_image="python:3.11", workdir="/w", timeout_sec=300
                ),
                setup=SetupSpec(commands=[]),
                run=RunSpec(command="test"),
                validation=None,
                harness_min_version=None,
                labels=None,
                source_path=Path("/path"),
            )

    def test_task_spec_source_path_serializes_to_string(self):
        """TaskSpec source_path serializes to string in JSON."""
        task = self.make_valid_task_spec()
        json_data = json.loads(task.model_dump_json())
        assert isinstance(json_data["source_path"], str)
        assert "task.yaml" in json_data["source_path"]

    def test_task_spec_round_trip(self):
        """TaskSpec can be serialized and deserialized."""
        original = self.make_valid_task_spec()
        json_data = json.loads(original.model_dump_json())
        restored = TaskSpec.model_validate(json_data)

        assert restored.id == original.id
        assert restored.suite == original.suite
        assert restored.repo.url == original.repo.url
        assert restored.environment.timeout_sec == original.environment.timeout_sec


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_validation_result_valid(self):
        """ValidationResult for valid baseline."""
        result = ValidationResult(
            task_id="test-task-1",
            valid=True,
            exit_code=1,  # Tests failed as expected
            stdout_path=Path("/logs/stdout.txt"),
            stderr_path=Path("/logs/stderr.txt"),
            error_reason=None,
            duration_sec=45.5,
        )

        assert result.valid is True
        assert result.exit_code == 1
        assert result.error_reason is None

    def test_validation_result_invalid(self):
        """ValidationResult for invalid baseline."""
        from agentbench.scoring import FailureReason

        result = ValidationResult(
            task_id="test-task-1",
            valid=False,
            exit_code=0,  # Tests passed (bad - baseline should fail)
            stdout_path=Path("/logs/stdout.txt"),
            stderr_path=Path("/logs/stderr.txt"),
            error_reason=FailureReason.BASELINE_NOT_FAILING,
            duration_sec=30.0,
        )

        assert result.valid is False
        assert result.exit_code == 0
        assert result.error_reason == FailureReason.BASELINE_NOT_FAILING

    def test_validation_result_paths_serialize_to_string(self):
        """ValidationResult paths serialize to strings."""
        result = ValidationResult(
            task_id="test-task-1",
            valid=True,
            exit_code=1,
            stdout_path=Path("/logs/stdout.txt"),
            stderr_path=Path("/logs/stderr.txt"),
            error_reason=None,
            duration_sec=45.5,
        )

        json_data = json.loads(result.model_dump_json())
        assert isinstance(json_data["stdout_path"], str)
        assert isinstance(json_data["stderr_path"], str)

    def test_validation_result_with_none_paths(self):
        """ValidationResult can have None paths."""
        result = ValidationResult(
            task_id="test-task-1",
            valid=False,
            exit_code=-1,
            stdout_path=None,
            stderr_path=None,
            error_reason=None,
            duration_sec=0.0,
        )

        assert result.stdout_path is None
        assert result.stderr_path is None

    def test_validation_result_requires_task_id(self):
        """ValidationResult requires task_id field."""
        with pytest.raises(ValidationError):
            ValidationResult(
                valid=True,
                exit_code=1,
                stdout_path=None,
                stderr_path=None,
                error_reason=None,
                duration_sec=10.0,
            )
