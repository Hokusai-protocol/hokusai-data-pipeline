"""Unit tests for logging utilities."""

import pytest
import logging
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock, call
import tempfile
import os

from src.utils.logging_utils import PipelineLogger, get_pipeline_logger, LogContext
from src.utils.constants import LOG_FORMAT, LOG_DATE_FORMAT


class TestPipelineLogger:
    """Test suite for PipelineLogger class."""

    def test_initialization_defaults(self):
        """Test logger initialization with defaults."""
        logger = PipelineLogger("test_logger")

        assert logger.name == "test_logger"
        assert logger.log_level == logging.INFO
        assert logger.log_dir is None
        assert logger.use_rich is True

    def test_initialization_custom(self):
        """Test logger initialization with custom settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"
            logger = PipelineLogger(
                "custom_logger",
                log_level="DEBUG",
                log_dir=log_dir,
                use_rich=False
            )

            assert logger.name == "custom_logger"
            assert logger.log_level == logging.DEBUG
            assert logger.log_dir == log_dir
            assert logger.use_rich is False

    @patch("src.utils.logging_utils.RichHandler")
    @patch("src.utils.logging_utils.Console")
    def test_setup_logger_with_rich(self, mock_console, mock_rich_handler):
        """Test logger setup with Rich handler."""
        mock_console_instance = Mock()
        mock_console.return_value = mock_console_instance
        mock_handler_instance = Mock()
        mock_rich_handler.return_value = mock_handler_instance

        logger = PipelineLogger("test_logger", use_rich=True)
        logger_obj = logger.get_logger()

        # Check that Rich handler was created
        mock_console.assert_called_once_with(stderr=True)
        mock_rich_handler.assert_called_once_with(
            console=mock_console_instance,
            show_time=True,
            show_path=False
        )

        # Check handler was added
        assert mock_handler_instance.setLevel.called

    def test_setup_logger_without_rich(self):
        """Test logger setup without Rich handler."""
        logger = PipelineLogger("test_logger", use_rich=False)
        logger_obj = logger.get_logger()

        # Should have at least one handler
        assert len(logger_obj.handlers) > 0

        # Handler should be StreamHandler
        handler = logger_obj.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream == sys.stdout

    def test_setup_logger_with_file_handler(self):
        """Test logger setup with file handler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"
            logger = PipelineLogger("test_logger", log_dir=log_dir)
            logger_obj = logger.get_logger()

            # Check that log directory was created
            assert log_dir.exists()

            # Should have multiple handlers (console + file)
            assert len(logger_obj.handlers) >= 2

            # Check for file handler
            file_handlers = [h for h in logger_obj.handlers if isinstance(h, logging.FileHandler)]
            assert len(file_handlers) == 1

            # Check log file was created
            log_files = list(log_dir.glob("test_logger_*.log"))
            assert len(log_files) == 1

    def test_get_logger(self):
        """Test getting the configured logger."""
        pipeline_logger = PipelineLogger("test_logger")
        logger = pipeline_logger.get_logger()

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"
        assert logger.level == logging.INFO

    def test_log_level_setting(self):
        """Test different log level settings."""
        # Test each valid log level
        for level_str, level_int in [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL)
        ]:
            logger = PipelineLogger("test", log_level=level_str)
            assert logger.log_level == level_int
            assert logger.get_logger().level == level_int


class TestGetPipelineLogger:
    """Test suite for get_pipeline_logger function."""

    @patch("src.utils.logging_utils.PipelineLogger")
    def test_get_pipeline_logger_defaults(self, mock_pipeline_logger):
        """Test getting logger with defaults."""
        mock_logger_instance = Mock()
        mock_pipeline_logger.return_value = mock_logger_instance
        mock_logger_instance.get_logger.return_value = Mock(spec=logging.Logger)

        result = get_pipeline_logger()

        mock_pipeline_logger.assert_called_once_with("hokusai_pipeline", "INFO", None)
        mock_logger_instance.get_logger.assert_called_once()

    @patch("src.utils.logging_utils.PipelineLogger")
    def test_get_pipeline_logger_custom(self, mock_pipeline_logger):
        """Test getting logger with custom settings."""
        mock_logger_instance = Mock()
        mock_pipeline_logger.return_value = mock_logger_instance
        mock_logger_instance.get_logger.return_value = Mock(spec=logging.Logger)

        log_dir = Path("/tmp/logs")
        result = get_pipeline_logger(
            name="custom",
            log_level="DEBUG",
            log_dir=log_dir
        )

        mock_pipeline_logger.assert_called_once_with("custom", "DEBUG", log_dir)

    @patch.dict(os.environ, {"PIPELINE_LOG_LEVEL": "WARNING"})
    @patch("src.utils.logging_utils.PipelineLogger")
    def test_get_pipeline_logger_env_var(self, mock_pipeline_logger):
        """Test getting logger with environment variable."""
        mock_logger_instance = Mock()
        mock_pipeline_logger.return_value = mock_logger_instance
        mock_logger_instance.get_logger.return_value = Mock(spec=logging.Logger)

        result = get_pipeline_logger()

        mock_pipeline_logger.assert_called_once_with("hokusai_pipeline", "WARNING", None)


class TestLogContext:
    """Test suite for LogContext context manager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_logger = Mock(spec=logging.Logger)

    def test_context_success(self):
        """Test context manager with successful operation."""
        with LogContext(self.mock_logger, "test operation") as ctx:
            # Check that start was logged
            self.mock_logger.info.assert_called_with("Starting test operation")
            assert ctx.operation == "test operation"
            assert ctx.start_time is not None

        # Check that completion was logged
        assert self.mock_logger.info.call_count == 2
        completion_call = self.mock_logger.info.call_args_list[1]
        assert "Completed test operation in" in completion_call[0][0]
        assert "seconds" in completion_call[0][0]

    def test_context_with_exception(self):
        """Test context manager with exception."""
        test_exception = ValueError("Test error")

        with pytest.raises(ValueError):
            with LogContext(self.mock_logger, "failing operation"):
                self.mock_logger.info.assert_called_with("Starting failing operation")
                raise test_exception

        # Check that error was logged
        self.mock_logger.error.assert_called_once()
        error_call = self.mock_logger.error.call_args[0][0]
        assert "Failed failing operation after" in error_call
        assert "seconds: Test error" in error_call

    @patch("src.utils.logging_utils.datetime")
    def test_context_timing(self, mock_datetime):
        """Test context manager timing calculation."""
        # Mock datetime to control timing
        start_time = datetime(2024, 1, 15, 12, 0, 0)
        end_time = datetime(2024, 1, 15, 12, 0, 5)  # 5 seconds later

        mock_datetime.now.side_effect = [start_time, end_time]

        with LogContext(self.mock_logger, "timed operation"):
            pass

        # Check that duration was calculated correctly
        completion_call = self.mock_logger.info.call_args_list[1]
        assert "5.00 seconds" in completion_call[0][0]

    def test_context_does_not_suppress_exceptions(self):
        """Test that context manager doesn't suppress exceptions."""
        with pytest.raises(RuntimeError):
            with LogContext(self.mock_logger, "operation"):
                raise RuntimeError("Should not be suppressed")

        # Error should have been logged
        self.mock_logger.error.assert_called_once()

    def test_multiple_contexts(self):
        """Test using multiple log contexts."""
        with LogContext(self.mock_logger, "outer operation"):
            self.mock_logger.info.assert_called_with("Starting outer operation")

            with LogContext(self.mock_logger, "inner operation"):
                # Both operations should be logged
                assert self.mock_logger.info.call_count >= 2

        # All operations should be logged
        assert self.mock_logger.info.call_count == 4  # 2 starts + 2 completions
