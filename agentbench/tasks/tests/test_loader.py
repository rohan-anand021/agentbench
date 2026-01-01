from pathlib import Path

import pytest
import yaml

from agentbench.tasks.exceptions import InvalidTaskError, SuiteNotFoundError
from agentbench.tasks.loader import discover_tasks, load_suite, load_task
from agentbench.tasks.models import TaskSpec

# =============================================================================
# Sample YAML Content Fixtures
# =============================================================================


@pytest.fixture
def valid_task_yaml_content() -> dict:
    """Returns a valid task.yaml content as a dictionary."""
    return {
        "id": "test_task",
        "suite": "test-suite",
        "repo": {
            "url": "https://github.com/example/repo",
            "commit": "abc123def456",
        },
        "environment": {
            "docker_image": "ghcr.io/agentbench/py-runner:0.1.0",
            "workdir": "/workspace",
            "timeout_sec": 300,
        },
        "setup": {"commands": ["pip install --upgrade pip", "pip install ."]},
        "run": {"command": "pytest -q"},
    }


@pytest.fixture
def malformed_yaml_content() -> str:
    """Returns malformed YAML that cannot be parsed."""
    return """
id: test_task
suite: test-suite
repo:
  url: https://github.com/example/repo
  commit: abc123
  this_is_broken
    indentation: wrong
"""


@pytest.fixture
def incomplete_task_yaml_content() -> dict:
    """Returns task.yaml content missing required fields."""
    return {
        "id": "incomplete_task",
        "suite": "test-suite",
        # Missing: repo, environment, setup, run
    }


@pytest.fixture
def invalid_field_types_yaml_content() -> dict:
    """Returns task.yaml content with wrong field types."""
    return {
        "id": "bad_types_task",
        "suite": "test-suite",
        "repo": {"url": "https://github.com/example/repo", "commit": "abc123"},
        "environment": {
            "docker_image": "ghcr.io/agentbench/py-runner:0.1.0",
            "workdir": "/workspace",
            "timeout_sec": "not_an_integer",  # Should be int
        },
        "setup": {
            "commands": "should_be_a_list"  # Should be list[str]
        },
        "run": {"command": "pytest -q"},
    }


# =============================================================================
# Temporary Directory Fixtures
# =============================================================================


@pytest.fixture
def temp_task_dir(tmp_path: Path, valid_task_yaml_content: dict) -> Path:
    """
    Creates a temporary task directory with a valid task.yaml file.

    Structure:
        tmp_path/
            task_name/
                task.yaml

    Returns the path to the task.yaml file.
    """
    task_dir = tmp_path / "test_task"
    task_dir.mkdir(parents=True)

    task_yaml_path = task_dir / "task.yaml"
    with open(task_yaml_path, "w") as f:
        yaml.dump(valid_task_yaml_content, f)

    return task_yaml_path


@pytest.fixture
def temp_malformed_task_dir(
    tmp_path: Path, malformed_yaml_content: str
) -> Path:
    """
    Creates a temporary task directory with a malformed task.yaml file.

    Returns the path to the malformed task.yaml file.
    """
    task_dir = tmp_path / "malformed_task"
    task_dir.mkdir(parents=True)

    task_yaml_path = task_dir / "task.yaml"
    with open(task_yaml_path, "w") as f:
        f.write(malformed_yaml_content)

    return task_yaml_path


@pytest.fixture
def temp_incomplete_task_dir(
    tmp_path: Path, incomplete_task_yaml_content: dict
) -> Path:
    """
    Creates a temporary task directory with an incomplete task.yaml file.

    Returns the path to the incomplete task.yaml file.
    """
    task_dir = tmp_path / "incomplete_task"
    task_dir.mkdir(parents=True)

    task_yaml_path = task_dir / "task.yaml"
    with open(task_yaml_path, "w") as f:
        yaml.dump(incomplete_task_yaml_content, f)

    return task_yaml_path


@pytest.fixture
def temp_suite_dir(tmp_path: Path, valid_task_yaml_content: dict) -> Path:
    """
    Creates a temporary suite directory with multiple task subdirectories.

    Structure:
        tmp_path/
            tasks/
                test-suite/
                    task_one/
                        task.yaml
                    task_two/
                        task.yaml
                    task_three/
                        task.yaml

    Returns the path to the tasks root directory (tmp_path/tasks).
    """
    tasks_root = tmp_path / "tasks"
    suite_dir = tasks_root / "test-suite"

    # Create multiple tasks in the suite
    for i, task_name in enumerate(["task_one", "task_two", "task_three"]):
        task_dir = suite_dir / task_name
        task_dir.mkdir(parents=True)

        # Customize the task content for each task
        task_content = valid_task_yaml_content.copy()
        task_content["id"] = task_name

        task_yaml_path = task_dir / "task.yaml"
        with open(task_yaml_path, "w") as f:
            yaml.dump(task_content, f)

    return tasks_root


@pytest.fixture
def temp_suite_with_invalid_task(
    tmp_path: Path,
    valid_task_yaml_content: dict,
    incomplete_task_yaml_content: dict,
) -> Path:
    """
    Creates a temporary suite directory with both valid and invalid tasks.

    Structure:
        tmp_path/
            tasks/
                mixed-suite/
                    valid_task/
                        task.yaml  (valid)
                    invalid_task/
                        task.yaml  (incomplete/invalid)

    Returns the path to the tasks root directory.
    """
    tasks_root = tmp_path / "tasks"
    suite_dir = tasks_root / "mixed-suite"

    # Create valid task
    valid_task_dir = suite_dir / "valid_task"
    valid_task_dir.mkdir(parents=True)
    valid_content = valid_task_yaml_content.copy()
    valid_content["id"] = "valid_task"
    valid_content["suite"] = "mixed-suite"
    with open(valid_task_dir / "task.yaml", "w") as f:
        yaml.dump(valid_content, f)

    # Create invalid task
    invalid_task_dir = suite_dir / "invalid_task"
    invalid_task_dir.mkdir(parents=True)
    invalid_content = incomplete_task_yaml_content.copy()
    invalid_content["suite"] = "mixed-suite"
    with open(invalid_task_dir / "task.yaml", "w") as f:
        yaml.dump(invalid_content, f)

    return tasks_root


@pytest.fixture
def temp_empty_suite_dir(tmp_path: Path) -> Path:
    """
    Creates an empty suite directory (no tasks inside).

    Structure:
        tmp_path/
            tasks/
                empty-suite/

    Returns the path to the tasks root directory.
    """
    tasks_root = tmp_path / "tasks"
    suite_dir = tasks_root / "empty-suite"
    suite_dir.mkdir(parents=True)

    return tasks_root


# =============================================================================
# Tests - Add your tests below
# =============================================================================


# TODO: Test `load_task()` with valid task.yaml
def test_load_task(temp_task_dir: Path, valid_task_yaml_content: dict):
    """Test that load_task() correctly parses a valid task.yaml file."""
    loaded_task = load_task(temp_task_dir)

    assert isinstance(loaded_task, TaskSpec)
    assert loaded_task.id == valid_task_yaml_content["id"]
    assert loaded_task.suite == valid_task_yaml_content["suite"]
    assert loaded_task.repo.url == valid_task_yaml_content["repo"]["url"]
    assert loaded_task.repo.commit == valid_task_yaml_content["repo"]["commit"]
    assert (
        loaded_task.environment.docker_image
        == valid_task_yaml_content["environment"]["docker_image"]
    )
    assert (
        loaded_task.environment.workdir
        == valid_task_yaml_content["environment"]["workdir"]
    )
    assert (
        loaded_task.environment.timeout_sec
        == valid_task_yaml_content["environment"]["timeout_sec"]
    )
    assert (
        loaded_task.setup.commands
        == valid_task_yaml_content["setup"]["commands"]
    )
    assert loaded_task.run.command == valid_task_yaml_content["run"]["command"]
    assert loaded_task.source_path == temp_task_dir


# TODO: Test `load_task()` raises `InvalidTaskError` for malformed YAML
def test_load_task_malformed_yaml(temp_malformed_task_dir: Path):
    """Test that load_task() raises an error for malformed YAML."""
    with pytest.raises(Exception):  # yaml.YAMLError or similar
        load_task(temp_malformed_task_dir)


def test_load_task_incomplete_yaml(temp_incomplete_task_dir: Path):
    """Test that load_task() raises InvalidTaskError for incomplete task.yaml."""
    with pytest.raises(InvalidTaskError):
        load_task(temp_incomplete_task_dir)


# TODO: Test `discover_tasks()` finds all tasks in a directory
def test_discover_tasks(temp_suite_dir: Path):
    """Test that discover_tasks() finds all task.yaml files in a suite directory."""
    suite_path = temp_suite_dir / "test-suite"
    discovered = discover_tasks(suite_path)

    assert len(discovered) == 3
    # Should be sorted deterministically
    assert discovered == sorted(discovered)
    # All paths should point to task.yaml files
    for path in discovered:
        assert path.name == "task.yaml"
        assert path.exists()


def test_discover_tasks_empty_suite(temp_empty_suite_dir: Path):
    """Test that discover_tasks() returns empty list for suite with no tasks."""
    suite_path = temp_empty_suite_dir / "empty-suite"
    discovered = discover_tasks(suite_path)

    assert discovered == []


def test_discover_tasks_nonexistent_suite(tmp_path: Path):
    """Test that discover_tasks() raises SuiteNotFoundError for non-existent directory."""
    nonexistent_path = tmp_path / "does-not-exist"

    with pytest.raises(SuiteNotFoundError):
        discover_tasks(nonexistent_path)


# TODO: Test `load_suite()` returns all valid tasks
def test_load_suite(temp_suite_dir: Path):
    """Test that load_suite() loads all valid tasks in a suite."""
    tasks = load_suite(temp_suite_dir, "test-suite")

    assert len(tasks) == 3
    assert all(isinstance(t, TaskSpec) for t in tasks)

    task_ids = {t.id for t in tasks}
    assert task_ids == {"task_one", "task_two", "task_three"}


def test_load_suite_with_invalid_task(temp_suite_with_invalid_task: Path):
    """Test that load_suite() skips invalid tasks and returns only valid ones."""
    tasks = load_suite(temp_suite_with_invalid_task, "mixed-suite")

    # Should only return the valid task, skipping the invalid one
    assert len(tasks) == 1
    assert tasks[0].id == "valid_task"


def test_load_suite_empty(temp_empty_suite_dir: Path):
    """Test that load_suite() returns empty list for suite with no tasks."""
    tasks = load_suite(temp_empty_suite_dir, "empty-suite")

    assert tasks == []


def test_load_suite_nonexistent(tmp_path: Path):
    """Test that load_suite() raises SuiteNotFoundError for non-existent suite."""
    with pytest.raises(SuiteNotFoundError):
        load_suite(tmp_path, "nonexistent-suite")
