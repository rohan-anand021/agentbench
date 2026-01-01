"""Tests for timeout utilities."""

import signal
import time
import pytest

from agentbench.util.timeout import (
    ToolTimeoutError,
    with_timeout,
    TOOL_TIMEOUTS,
)


class TestToolTimeoutError:
    """Tests for ToolTimeoutError exception."""

    def test_timeout_error_message(self) -> None:
        """Test that error message includes seconds and operation."""
        error = ToolTimeoutError(30, "list_files")
        assert "30" in str(error)
        assert "list_files" in str(error)
        assert error.seconds == 30
        assert error.operation == "list_files"

    def test_timeout_error_default_operation(self) -> None:
        """Test default operation name."""
        error = ToolTimeoutError(10)
        assert "Operation" in str(error)


class TestWithTimeoutDecorator:
    """Tests for the with_timeout decorator."""

    def test_fast_function_completes(self) -> None:
        """Function that completes in time returns normally."""
        @with_timeout(5, "test_op")
        def fast_function() -> str:
            return "done"

        result = fast_function()
        assert result == "done"

    def test_slow_function_times_out(self) -> None:
        """Function that exceeds timeout raises ToolTimeoutError."""
        @with_timeout(1, "slow_op")
        def slow_function() -> str:
            time.sleep(5)
            return "done"

        with pytest.raises(ToolTimeoutError) as exc_info:
            slow_function()
        
        assert exc_info.value.seconds == 1
        assert exc_info.value.operation == "slow_op"

    def test_preserves_function_metadata(self) -> None:
        """Decorator preserves function name and docstring."""
        @with_timeout(10, "test")
        def my_function() -> None:
            """My docstring."""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_passes_arguments(self) -> None:
        """Decorator correctly passes arguments to wrapped function."""
        @with_timeout(5, "test")
        def add(a: int, b: int) -> int:
            return a + b

        result = add(2, 3)
        assert result == 5

    def test_passes_keyword_arguments(self) -> None:
        """Decorator correctly passes keyword arguments."""
        @with_timeout(5, "test")
        def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}!"

        result = greet("World", greeting="Hi")
        assert result == "Hi, World!"


class TestToolTimeouts:
    """Tests for TOOL_TIMEOUTS configuration."""

    def test_all_tools_have_timeouts(self) -> None:
        """All expected tools have timeout values."""
        expected_tools = ["list_files", "read_file", "search", "apply_patch", "run"]
        for tool in expected_tools:
            assert tool in TOOL_TIMEOUTS

    def test_run_timeout_is_none(self) -> None:
        """run tool uses dynamic timeout from params."""
        assert TOOL_TIMEOUTS["run"] is None

    def test_list_files_timeout(self) -> None:
        """list_files has 30s timeout."""
        assert TOOL_TIMEOUTS["list_files"] == 30

    def test_read_file_timeout(self) -> None:
        """read_file has 10s timeout."""
        assert TOOL_TIMEOUTS["read_file"] == 10

    def test_search_timeout(self) -> None:
        """search has 60s timeout."""
        assert TOOL_TIMEOUTS["search"] == 60

    def test_apply_patch_timeout(self) -> None:
        """apply_patch has 10s timeout."""
        assert TOOL_TIMEOUTS["apply_patch"] == 10
