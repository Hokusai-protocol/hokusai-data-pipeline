"""Logging utilities for the pipeline."""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from rich.logging import RichHandler
from rich.console import Console

from src.utils.constants import LOG_FORMAT, LOG_DATE_FORMAT


class PipelineLogger:
    """Custom logger for the Hokusai pipeline."""
    
    def __init__(
        self,
        name: str,
        log_level: str = "INFO",
        log_dir: Optional[Path] = None,
        use_rich: bool = True
    ):
        self.name = name
        self.log_level = getattr(logging, log_level.upper())
        self.log_dir = log_dir
        self.use_rich = use_rich
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """Set up the logger with handlers."""
        logger = logging.getLogger(self.name)
        logger.setLevel(self.log_level)
        
        # Remove existing handlers
        logger.handlers.clear()
        
        # Console handler with Rich formatting
        if self.use_rich:
            console_handler = RichHandler(
                console=Console(stderr=True),
                show_time=True,
                show_path=False
            )
        else:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(
                logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
            )
        
        console_handler.setLevel(self.log_level)
        logger.addHandler(console_handler)
        
        # File handler if log directory provided
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = self.log_dir / f"{self.name}_{timestamp}.log"
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(
                logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
            )
            logger.addHandler(file_handler)
        
        return logger
    
    def get_logger(self) -> logging.Logger:
        """Get the configured logger."""
        return self.logger


def get_pipeline_logger(
    name: str = "hokusai_pipeline",
    log_level: Optional[str] = None,
    log_dir: Optional[Path] = None
) -> logging.Logger:
    """Get a pipeline logger instance.
    
    Args:
        name: Logger name
        log_level: Logging level (defaults to env var or INFO)
        log_dir: Directory for log files
        
    Returns:
        Configured logger
    """
    if log_level is None:
        import os
        log_level = os.getenv("PIPELINE_LOG_LEVEL", "INFO")
    
    pipeline_logger = PipelineLogger(name, log_level, log_dir)
    return pipeline_logger.get_logger()


class LogContext:
    """Context manager for logging operations."""
    
    def __init__(self, logger: logging.Logger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.info(f"Starting {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.info(
                f"Completed {self.operation} in {duration:.2f} seconds"
            )
        else:
            self.logger.error(
                f"Failed {self.operation} after {duration:.2f} seconds: {exc_val}"
            )
        
        return False  # Don't suppress exceptions