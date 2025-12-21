import logging
from pathlib import Path

from agentbench.tasks.exceptions import InvalidTaskError

logger = logging.getLogger(__name__)


def validate_task_yaml(task: dict, task_yaml: Path) -> None:
    required_structure = {
        "id": str,
        "suite": str,
        "repo": {
            "url": str,
            "commit": str,
        },
        "environment": {
            "docker_image": str,
            "workdir": str,
            "timeout_sec": int,
        },
        "setup": {
            "commands": list,
        },
        "run": {
            "command": str,
        },
    }

    def validate(node, schema, path=""):
        if not isinstance(node, dict):
            raise TypeError(f"{path or 'root'} must be a mapping")

        for key, expected in schema.items():
            if key not in node:
                raise KeyError(f"Missing key: {path + key}")

            value = node[key]

            if isinstance(expected, dict):
                validate(value, expected, path + key + ".")
            else:
                if not isinstance(value, expected):
                    raise TypeError(
                        f"Key '{path + key}' must be of type "
                        f"{expected.__name__}, got {type(value).__name__}"
                    )

    try:
        validate(task, required_structure)
    except Exception as e:
        logger.error("Task validation failed for %s: %s", task_yaml, e)
        raise InvalidTaskError(task_yaml, e) from e

    logger.debug("Task validation passed for %s", task_yaml)
