"""Unit tests for logging configuration."""

import logging
from io import StringIO

import pytest

from agentbench.logging import get_logger, setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_creates_handler(self):
        """setup_logging attaches a handler to the agentbench logger."""
        # Get initial handler count
        logger = logging.getLogger("agentbench")
        initial_handlers = len(logger.handlers)

        setup_logging()

        # Should have added a handler
        assert len(logger.handlers) > initial_handlers

        # Cleanup: remove added handlers
        while len(logger.handlers) > initial_handlers:
            logger.handlers.pop()

    def test_setup_logging_with_custom_level(self):
        """setup_logging respects custom log level."""
        logger = logging.getLogger("agentbench")
        initial_handlers = len(logger.handlers)

        setup_logging(level=logging.DEBUG)

        assert logger.level == logging.DEBUG

        # Cleanup
        while len(logger.handlers) > initial_handlers:
            logger.handlers.pop()
        logger.setLevel(logging.WARNING)  # Reset to default

    def test_logger_propagate_is_false(self):
        """Logger propagation is disabled to avoid duplicate logs."""
        logger = logging.getLogger("agentbench")
        initial_handlers = len(logger.handlers)

        setup_logging()

        assert logger.propagate is False

        # Cleanup
        while len(logger.handlers) > initial_handlers:
            logger.handlers.pop()

    def test_setup_logging_formatter(self):
        """setup_logging configures formatter with timestamp and level."""
        logger = logging.getLogger("agentbench")
        initial_handlers = len(logger.handlers)

        setup_logging()

        # Check that at least one handler has a formatter
        handlers_with_formatter = [
            h for h in logger.handlers if h.formatter is not None
        ]
        assert len(handlers_with_formatter) > 0

        # Cleanup
        while len(logger.handlers) > initial_handlers:
            logger.handlers.pop()


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger_instance(self):
        """get_logger returns a Logger instance."""
        result = get_logger("test.module")
        assert isinstance(result, logging.Logger)

    def test_get_logger_uses_provided_name(self):
        """get_logger returns logger with the specified name."""
        result = get_logger("my.custom.module")
        assert result.name == "my.custom.module"

    def test_get_logger_same_name_returns_same_logger(self):
        """Calling get_logger with same name returns same logger instance."""
        logger1 = get_logger("shared.module")
        logger2 = get_logger("shared.module")
        assert logger1 is logger2
