"""
Unit Tests for Logging Setup

Targets: jenezis/utils/logging.py
Coverage: 19% -> 90%+
"""
import pytest
import logging

from jenezis.utils.logging import setup_logging

pytestmark = pytest.mark.unit


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_configures_root_logger(self):
        """Setup configures the root logger."""
        # Clear any existing handlers first
        root = logging.getLogger()
        original_handlers = root.handlers.copy()
        original_level = root.level

        try:
            setup_logging()

            assert root.level == logging.INFO
            assert len(root.handlers) > 0

        finally:
            # Restore original state
            root.handlers = original_handlers
            root.level = original_level

    def test_setup_logging_clears_existing_handlers(self):
        """Setup clears existing handlers."""
        root = logging.getLogger()
        original_handlers = root.handlers.copy()

        try:
            # Add a dummy handler
            root.addHandler(logging.StreamHandler())

            setup_logging()

            # Should have only the JSON handler now
            assert len(root.handlers) == 1

        finally:
            root.handlers = original_handlers

    def test_setup_logging_uses_json_formatter(self):
        """Setup uses JSON formatter."""
        root = logging.getLogger()
        original_handlers = root.handlers.copy()

        try:
            setup_logging()

            handler = root.handlers[0]
            formatter = handler.formatter
            assert formatter is not None
            assert "JsonFormatter" in type(formatter).__name__

        finally:
            root.handlers = original_handlers

    def test_setup_logging_suppresses_verbose_loggers(self):
        """Setup suppresses verbose library loggers."""
        root = logging.getLogger()
        original_handlers = root.handlers.copy()

        try:
            setup_logging()

            # Check that verbose loggers are suppressed
            assert logging.getLogger("uvicorn").level >= logging.WARNING
            assert logging.getLogger("sqlalchemy.engine").level >= logging.WARNING
            assert logging.getLogger("boto3").level >= logging.WARNING
            assert logging.getLogger("botocore").level >= logging.WARNING

        finally:
            root.handlers = original_handlers

    def test_setup_logging_can_be_called_multiple_times(self):
        """Setup can be called multiple times without error."""
        root = logging.getLogger()
        original_handlers = root.handlers.copy()

        try:
            setup_logging()
            setup_logging()  # Should not raise
            setup_logging()  # Should not raise

            # Should still have only one handler
            assert len(root.handlers) == 1

        finally:
            root.handlers = original_handlers
