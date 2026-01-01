"""Timeout enforcement utilities for tool operations."""

import signal
from functools import wraps
from typing import Callable, TypeVar, ParamSpec

P = ParamSpec("P")
R = TypeVar("R")


class ToolTimeoutError(Exception):
    """Raised when a tool operation times out."""
    
    def __init__(self, seconds: int, operation: str = "Operation"):
        self.seconds = seconds
        self.operation = operation
        super().__init__(f"{operation} timed out after {seconds}s")


def with_timeout(seconds: int, operation: str = "Operation") -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to add timeout to a function.
    
    Uses SIGALRM on Unix systems. Note: this does not work on Windows.
    
    Args:
        seconds: Maximum time allowed for the operation
        operation: Description of the operation for error messages
    
    Returns:
        Decorated function that will raise ToolTimeoutError if it exceeds the timeout
    
    Example:
        @with_timeout(30, "list_files")
        def list_files(...):
            ...
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            def handler(signum: int, frame: object) -> None:
                raise ToolTimeoutError(seconds, operation)
            
            # Save the old handler and set the alarm
            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.alarm(seconds)
            try:
                return func(*args, **kwargs)
            finally:
                # Cancel the alarm and restore old handler
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        return wrapper
    return decorator


# Default timeouts for each tool
TOOL_TIMEOUTS = {
    "list_files": 30,   # Should be fast
    "read_file": 10,    # File read operations
    "search": 60,       # ripgrep is fast but may scan many files
    "apply_patch": 10,  # Patch application
    "run": None,        # Uses params.timeout_sec or task default
}
