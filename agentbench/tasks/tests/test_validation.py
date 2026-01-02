"""Unit tests for task YAML validation."""

from pathlib import Path

import pytest

from agentbench.tasks.exceptions import InvalidTaskError
from agentbench.tasks.validation import validate_task_yaml


def make_valid_task_dict() -> dict:
    """Helper to create a valid task dictionary."""
    return {
        "task_spec_version": "1.0",
        "id": "test-task-1",
        "suite": "test-suite",
        "repo": {
            "url": "https://github.com/example/repo.git",
            "commit": "abc123",
        },
        "environment": {
            "docker_image": "python:3.11",
            "workdir": "/workspace",
            "timeout_sec": 300,
        },
        "setup": {
            "commands": ["pip install -e ."],
        },
        "run": {
            "command": "pytest tests/",
        },
        "harness_min_version": "0.1.0",
        "labels": ["smoke"],
        "validation": {
            "expected_exit_codes": [1],
        },
    }


class TestValidateTaskYaml:
    """Tests for validate_task_yaml function."""

    def test_valid_task_passes_validation(self, tmp_path: Path):
        """Valid task dictionary passes validation."""
        task = make_valid_task_dict()
        task_path = tmp_path / "task.yaml"

        # Should not raise
        validate_task_yaml(task, task_path)

    def test_missing_id_raises_error(self, tmp_path: Path):
        """Missing 'id' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["id"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_task_spec_version_raises_error(self, tmp_path: Path):
        """Missing 'task_spec_version' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["task_spec_version"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_suite_raises_error(self, tmp_path: Path):
        """Missing 'suite' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["suite"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_repo_raises_error(self, tmp_path: Path):
        """Missing 'repo' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["repo"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_repo_url_raises_error(self, tmp_path: Path):
        """Missing 'repo.url' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["repo"]["url"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_repo_commit_raises_error(self, tmp_path: Path):
        """Missing 'repo.commit' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["repo"]["commit"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_environment_raises_error(self, tmp_path: Path):
        """Missing 'environment' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["environment"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_docker_image_raises_error(self, tmp_path: Path):
        """Missing 'environment.docker_image' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["environment"]["docker_image"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_workdir_raises_error(self, tmp_path: Path):
        """Missing 'environment.workdir' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["environment"]["workdir"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_timeout_raises_error(self, tmp_path: Path):
        """Missing 'environment.timeout_sec' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["environment"]["timeout_sec"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_setup_raises_error(self, tmp_path: Path):
        """Missing 'setup' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["setup"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_setup_commands_raises_error(self, tmp_path: Path):
        """Missing 'setup.commands' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["setup"]["commands"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_run_raises_error(self, tmp_path: Path):
        """Missing 'run' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["run"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_missing_run_command_raises_error(self, tmp_path: Path):
        """Missing 'run.command' field raises InvalidTaskError."""
        task = make_valid_task_dict()
        del task["run"]["command"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_unexpected_key_raises_error(self, tmp_path: Path):
        """Unexpected keys raise InvalidTaskError."""
        task = make_valid_task_dict()
        task["extra_key"] = "nope"
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_invalid_task_spec_version_raises_error(self, tmp_path: Path):
        """Unsupported task_spec_version should raise InvalidTaskError."""
        task = make_valid_task_dict()
        task["task_spec_version"] = "99.0"
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_invalid_regex_raises_error(self, tmp_path: Path):
        """Invalid regex in validation hints should raise InvalidTaskError."""
        task = make_valid_task_dict()
        task["validation"]["expected_failure_regex"] = "("
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)


class TestValidateTaskYamlTypes:
    """Tests for type validation in validate_task_yaml."""

    def test_id_must_be_string(self, tmp_path: Path):
        """'id' field must be a string."""
        task = make_valid_task_dict()
        task["id"] = 123
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_suite_must_be_string(self, tmp_path: Path):
        """'suite' field must be a string."""
        task = make_valid_task_dict()
        task["suite"] = ["test-suite"]
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_timeout_must_be_int(self, tmp_path: Path):
        """'environment.timeout_sec' must be an integer."""
        task = make_valid_task_dict()
        task["environment"]["timeout_sec"] = "300"
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_commands_must_be_list(self, tmp_path: Path):
        """'setup.commands' must be a list."""
        task = make_valid_task_dict()
        task["setup"]["commands"] = "pip install -e ."
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)

    def test_repo_must_be_dict(self, tmp_path: Path):
        """'repo' field must be a dictionary."""
        task = make_valid_task_dict()
        task["repo"] = "https://github.com/example/repo.git"
        task_path = tmp_path / "task.yaml"

        with pytest.raises(InvalidTaskError):
            validate_task_yaml(task, task_path)


class TestValidateTaskYamlEmptyValues:
    """Tests for empty value handling."""

    def test_empty_commands_list_is_valid(self, tmp_path: Path):
        """Empty 'setup.commands' list is valid."""
        task = make_valid_task_dict()
        task["setup"]["commands"] = []
        task_path = tmp_path / "task.yaml"

        # Should not raise
        validate_task_yaml(task, task_path)

    def test_empty_id_is_valid_structure(self, tmp_path: Path):
        """Empty string 'id' is structurally valid (type check passes)."""
        task = make_valid_task_dict()
        task["id"] = ""
        task_path = tmp_path / "task.yaml"

        # Structure validation passes (empty string is still a string)
        validate_task_yaml(task, task_path)
