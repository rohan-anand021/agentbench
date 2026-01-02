import logging
import re
from importlib import metadata
from pathlib import Path

from agentbench.tasks.exceptions import InvalidTaskError

logger = logging.getLogger(__name__)


class ListOf:
    def __init__(self, item_type: type):
        self.item_type = item_type


class Schema:
    def __init__(
        self,
        required: dict[str, object],
        optional: dict[str, object] | None = None,
    ):
        self.required = required
        self.optional = optional or {}


SUPPORTED_TASK_SPEC_VERSIONS = {"1.0"}


def _parse_version(version: str) -> tuple[int, int, int] | None:
    try:
        parts = version.split(".")
        numeric = [int(part) for part in parts if part != ""]
    except ValueError:
        return None

    if not numeric:
        return None

    while len(numeric) < 3:
        numeric.append(0)
    return tuple(numeric[:3])


def _get_harness_version() -> str | None:
    try:
        return metadata.version("agentbench")
    except metadata.PackageNotFoundError:
        return None


def validate_task_yaml(task: dict, task_yaml: Path) -> None:
    required_structure = Schema(
        required={
            "task_spec_version": str,
            "id": str,
            "suite": str,
            "repo": Schema(
                required={
                    "url": str,
                    "commit": str,
                }
            ),
            "environment": Schema(
                required={
                    "docker_image": str,
                    "workdir": str,
                    "timeout_sec": int,
                }
            ),
            "setup": Schema(
                required={
                    "commands": ListOf(str),
                }
            ),
            "run": Schema(
                required={
                    "command": str,
                }
            ),
        },
        optional={
            "validation": Schema(
                required={},
                optional={
                    "expected_exit_codes": ListOf(int),
                    "expected_failure_regex": str,
                    "expected_stdout_regex": str,
                    "expected_stderr_regex": str,
                    "disallowed_failure_regex": ListOf(str),
                    "expected_failing_tests": ListOf(str),
                },
            ),
            "harness_min_version": str,
            "labels": ListOf(str),
            "agent": Schema(
                required={
                    "entrypoint": str,
                    "max_steps": int,
                }
            ),
        },
    )

    def validate(node, schema: Schema, path=""):
        if not isinstance(node, dict):
            raise TypeError(f"{path or 'root'} must be a mapping")

        allowed = set(schema.required.keys()) | set(schema.optional.keys())
        for key in node:
            if key not in allowed:
                raise KeyError(f"Unexpected key: {path + key}")

        for key, expected in schema.required.items():
            if key not in node:
                raise KeyError(f"Missing key: {path + key}")
            value = node[key]
            validate_value(value, expected, path + key)

        for key, expected in schema.optional.items():
            if key in node:
                value = node[key]
                validate_value(value, expected, path + key)

    def validate_value(value, expected, path):
        if isinstance(expected, Schema):
            validate(value, expected, path + ".")
            return
        if isinstance(expected, ListOf):
            if not isinstance(value, list):
                raise TypeError(
                    f"Key '{path}' must be a list, got {type(value).__name__}"
                )
            for idx, item in enumerate(value):
                if not isinstance(item, expected.item_type):
                    raise TypeError(
                        f"Key '{path}[{idx}]' must be of type "
                        f"{expected.item_type.__name__}, got {type(item).__name__}"
                    )
            return
        if isinstance(expected, tuple):
            if not isinstance(value, expected):
                expected_names = ", ".join(t.__name__ for t in expected)
                raise TypeError(
                    f"Key '{path}' must be of type {expected_names}, "
                    f"got {type(value).__name__}"
                )
            return
        if not isinstance(value, expected):
            raise TypeError(
                f"Key '{path}' must be of type "
                f"{expected.__name__}, got {type(value).__name__}"
            )

    try:
        validate(task, required_structure)

        spec_version = task.get("task_spec_version", "")
        if spec_version not in SUPPORTED_TASK_SPEC_VERSIONS:
            raise ValueError(
                f"Unsupported task_spec_version: {spec_version}. "
                f"Supported versions: {sorted(SUPPORTED_TASK_SPEC_VERSIONS)}"
            )

        validation = task.get("validation", {}) or {}
        for key in (
            "expected_failure_regex",
            "expected_stdout_regex",
            "expected_stderr_regex",
        ):
            if key in validation and validation[key] is not None:
                re.compile(validation[key])

        if "disallowed_failure_regex" in validation and validation["disallowed_failure_regex"]:
            for pattern in validation["disallowed_failure_regex"]:
                re.compile(pattern)

        harness_min_version = task.get("harness_min_version")
        if harness_min_version:
            parsed_required = _parse_version(harness_min_version)
            if parsed_required is None:
                raise ValueError(
                    f"harness_min_version must be a semantic version, got {harness_min_version}"
                )
            current_version = _get_harness_version()
            parsed_current = _parse_version(current_version) if current_version else None
            if parsed_current and parsed_current < parsed_required:
                raise ValueError(
                    f"Harness version {current_version} is below required {harness_min_version}"
                )
    except Exception as e:
        logger.error("Task validation failed for %s: %s", task_yaml, e)
        raise InvalidTaskError(task_yaml, e) from e

    logger.debug("Task validation passed for %s", task_yaml)
