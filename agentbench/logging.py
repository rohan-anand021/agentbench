"""Logging configuration for agentbench."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure logging for the agentbench package.

    Args:
        level: The logging level to use. Defaults to INFO.
    """
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    # Configure the root agentbench logger
    logger = logging.getLogger("agentbench")
    logger.setLevel(level)
    logger.addHandler(handler)

    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: The module name, typically __name__.

    Returns:
        A configured logger instance.
    """
    return logging.getLogger(name)
