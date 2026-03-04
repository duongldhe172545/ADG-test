"""
Logging Configuration
Centralized logging for the ADG Knowledge Management System.
"""

import logging
import sys

from backend.config import settings


def get_logger(name: str = "adg") -> logging.Logger:
    """Get a configured logger instance."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        level = logging.DEBUG if settings.DEBUG else logging.INFO
        logger.setLevel(level)
        handler.setLevel(level)

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
