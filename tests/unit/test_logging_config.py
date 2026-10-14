"""Tests for the logging setup."""

import logging

from drupal_mcp_server.logging_config import get_logger, setup_logging


def _server_handlers() -> list[logging.Handler]:
    return logging.getLogger("drupal_mcp_server").handlers


def test_configures_the_server_logger() -> None:
    logger = setup_logging()
    assert logger.name == "drupal_mcp_server"
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


def test_returns_a_logger_usable_immediately() -> None:
    logger = get_logger("clients")
    logger.info("boom")
    assert logger.name == "drupal_mcp_server.clients"


def test_level_is_applied_case_insensitively() -> None:
    logger = setup_logging("debug")
    assert logger.level == logging.DEBUG
    setup_logging("INFO")  # leave the process usable for other tests


def test_unknown_level_falls_back_to_info() -> None:
    logger = setup_logging("not-a-level")
    assert logger.level == logging.INFO


def test_repeated_setup_does_not_stack_handlers() -> None:
    """Each call used to append another handler, so every message was logged
    once per call: a server reconfigured at runtime would print duplicates."""
    for _ in range(5):
        setup_logging()
    handlers = _server_handlers()
    assert len(handlers) <= 1, f"{len(handlers)} handlers after repeated setup"
