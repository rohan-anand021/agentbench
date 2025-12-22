"""Unit tests for task exceptions."""

from pathlib import Path

import pytest

from agentbench.tasks.exceptions import (
    InvalidTaskError,
    SuiteNotFoundError,
    TaskNotFoundError,
)


class TestInvalidTaskError:
    """Tests for InvalidTaskError exception."""

    def test_invalid_task_error_message_format(self):
        """InvalidTaskError message includes file path and original error."""
        task_path = Path("/path/to/task.yaml")
        original_error = ValueError("Missing required field: id")

        error = InvalidTaskError(task_path, original_error)

        assert "task.yaml" in str(error)
        assert "Missing required field" in str(error)

    def test_invalid_task_error_is_exception(self):
        """InvalidTaskError is an Exception subclass."""
        task_path = Path("/path/to/task.yaml")
        original_error = ValueError("test")

        error = InvalidTaskError(task_path, original_error)

        assert isinstance(error, Exception)

    def test_invalid_task_error_can_be_raised_and_caught(self):
        """InvalidTaskError can be raised and caught."""
        task_path = Path("/path/to/task.yaml")
        original_error = ValueError("test")

        with pytest.raises(InvalidTaskError):
            raise InvalidTaskError(task_path, original_error)


class TestTaskNotFoundError:
    """Tests for TaskNotFoundError exception."""

    def test_task_not_found_error_is_exception(self):
        """TaskNotFoundError is an Exception subclass."""
        error = TaskNotFoundError("Task not found")
        assert isinstance(error, Exception)

    def test_task_not_found_error_can_be_raised_and_caught(self):
        """TaskNotFoundError can be raised and caught."""
        with pytest.raises(TaskNotFoundError):
            raise TaskNotFoundError("Task xyz not found")


class TestSuiteNotFoundError:
    """Tests for SuiteNotFoundError exception."""

    def test_suite_not_found_error_message_format(self):
        """SuiteNotFoundError message includes suite directory."""
        suite_dir = Path("/path/to/suites/my-suite")

        error = SuiteNotFoundError(suite_dir)

        assert "my-suite" in str(error)
        assert "not found" in str(error).lower()

    def test_suite_not_found_error_is_exception(self):
        """SuiteNotFoundError is an Exception subclass."""
        suite_dir = Path("/path/to/suite")
        error = SuiteNotFoundError(suite_dir)

        assert isinstance(error, Exception)

    def test_suite_not_found_error_can_be_raised_and_caught(self):
        """SuiteNotFoundError can be raised and caught."""
        suite_dir = Path("/path/to/suite")

        with pytest.raises(SuiteNotFoundError):
            raise SuiteNotFoundError(suite_dir)
