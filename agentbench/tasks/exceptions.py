from pathlib import Path


class InvalidTaskError(Exception):
    def __init__(self, task_yaml: Path, e: Exception):
        super().__init__(f"Invalid task YAML {str(task_yaml)}: {str(e)}")


class TaskNotFoundError(Exception):
    pass


class SuiteNotFoundError(Exception):
    """
    - `class SuiteNotFoundError(Exception)`:
    raised when suite directory doesn't exist
    """

    def __init__(self, suite_dir: Path):
        super().__init__(f"Suite directory not found: {suite_dir}")
