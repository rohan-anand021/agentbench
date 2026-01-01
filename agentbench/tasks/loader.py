import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from agentbench.tasks.exceptions import InvalidTaskError, SuiteNotFoundError
from agentbench.tasks.models import TaskSpec
from agentbench.tasks.validation import validate_task_yaml

logger = logging.getLogger(__name__)


def load_task(task_yaml: Path) -> TaskSpec:
    """
    Read and parse YAML file
    - Validate against schema (reuse validation logic from `run_task.py`)
    - Return `TaskSpec` object
    - Raise `InvalidTaskError` if validation fails
    """

    with open(task_yaml) as f:
        task = yaml.safe_load(f)

    validate_task_yaml(task, task_yaml)

    # validate task spec
    try:
        task_spec = TaskSpec(**task, source_path=task_yaml)
    except ValidationError as e:
        logger.error("Task spec validation failed for %s: %s", task_yaml, e)
        raise InvalidTaskError(task_yaml, e) from e

    logger.debug("Task loaded successfully: %s", task_spec.id)
    return task_spec


def discover_tasks(suite_dir: Path) -> list[Path]:
    """
    Use `pathlib.Path.glob("*/task.yaml")` to find all task.yaml files
    - Return sorted list of paths (deterministic ordering)
    """

    if not suite_dir.exists():
        logger.error("Suite directory does not exist: %s", suite_dir)
        raise SuiteNotFoundError(suite_dir)

    tasks = sorted(suite_dir.glob("*/task.yaml"))
    logger.debug("Discovered %d tasks in %s", len(tasks), suite_dir)
    return tasks


def load_suite(tasks_root: Path, suite_name: str) -> list[TaskSpec]:
    """
    Construct suite path: `tasks_root / suite_name`
    - Call `discover_tasks()` to find all task.yaml files
    - Call `load_task()` for each, collecting results
    - Log warning for any tasks that fail to load (don't crash entire suite)
    - Return list of successfully loaded `TaskSpec` objects
    """

    suite_path = Path(tasks_root / suite_name)
    all_tasks = []
    tasks: list[Path] = discover_tasks(suite_path)

    for task in tasks:
        try:
            loaded_task = load_task(task)
            all_tasks.append(loaded_task)
        except InvalidTaskError as e:
            logger.warning("Invalid task %s: %s", task, e)
            continue
        except Exception as e:
            logger.error("Error with task %s: %s", task, e)
            raise

    return all_tasks
