"""
Centralized logging configuration for FamilyBot.

This module provides comprehensive logging setup for both the main bot
and utility scripts, with file rotation, error categorization, and
security-conscious logging practices.
"""

import logging
import logging.handlers
import sys
from asyncio import Queue
from pathlib import Path
from typing import Optional
import re

import coloredlogs
from pythonjsonlogger import jsonlogger
from .web_logging import WebSocketQueueHandler

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def sanitize_log_message(message: str) -> str:
    """
    Sanitize log messages to remove or mask sensitive information.

    Args:
        message: Raw log message

    Returns:
        Sanitized log message with sensitive data masked
    """
    # Mask potential API keys (look for long alphanumeric strings)

    # Mask Steam API keys (32 character hex strings)
    message = re.sub(r'\b[A-F0-9]{32}\b', '[STEAM_API_KEY]', message, flags=re.IGNORECASE)

    # Mask Discord tokens (longer base64-like strings)
    message = re.sub(r'\b[A-Za-z0-9+/]{50,}\b', '[DISCORD_TOKEN]', message)

    # Mask potential passwords or secrets
    message = re.sub(r'(password|secret|key|token)[\s=:]+[^\s]+', r'\1=[MASKED]', message, flags=re.IGNORECASE)

    return message


def setup_bot_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Set up comprehensive logging for the main FamilyBot application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create main logger
    logger = logging.getLogger("familybot")
    logger.setLevel(numeric_level)

    # Clear any existing handlers to avoid duplicates
    logger.handlers.clear()


    # 1. Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_formatter = coloredlogs.ColoredFormatter(
        fmt='%(asctime)s - %(levelname)s - %(name)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 2. Main log file (all levels) - rotating
    main_log_file = logs_dir / "familybot.log"
    main_file_handler = logging.handlers.RotatingFileHandler(
        main_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    main_file_handler.setLevel(numeric_level)
    main_file_handler.setFormatter(jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s %(lineno)d %(pathname)s'
    ))
    logger.addHandler(main_file_handler)

    # 3. Error log file (WARNING and above) - rotating
    error_log_file = logs_dir / "familybot_errors.log"
    error_file_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=10,
        encoding='utf-8'
    )
    error_file_handler.setLevel(logging.WARNING)
    error_file_handler.setFormatter(jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s %(lineno)d %(pathname)s'
    ))
    logger.addHandler(error_file_handler)

    # 4. Steam API specific log file
    steam_log_file = logs_dir / "steam_api.log"
    steam_file_handler = logging.handlers.RotatingFileHandler(
        steam_log_file,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=5,
        encoding='utf-8'
    )
    steam_file_handler.setLevel(logging.INFO)
    steam_file_handler.setFormatter(jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s %(lineno)d %(pathname)s'
    ))

    # Create a filter for Steam API related logs
    class SteamAPIFilter(logging.Filter):
        def filter(self, record):
            return any(keyword in record.getMessage().lower() for keyword in [
                'steam', 'api', 'rate limit', 'private profile', 'success:2'
            ])

    steam_file_handler.addFilter(SteamAPIFilter())
    logger.addHandler(steam_file_handler)

    # Add a custom filter to sanitize all log messages
    class SanitizeFilter(logging.Filter):
        def filter(self, record):
            record.msg = sanitize_log_message(str(record.msg))
            return True

    # Apply sanitization to all handlers
    for handler in logger.handlers:
        handler.addFilter(SanitizeFilter())

    logger.info("Bot logging initialized - Level: %s, Logs dir: %s", log_level, logs_dir)
    return logger


def setup_script_logging(script_name: str, log_level: str = "INFO") -> logging.Logger:
    """
    Set up logging for utility scripts.

    Args:
        script_name: Name of the script (e.g., 'populate_database', 'populate_prices')
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    logs_dir = PROJECT_ROOT / "logs" / "scripts"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create script-specific logger
    logger = logging.getLogger(f"script.{script_name}")
    logger.setLevel(numeric_level)

    # Clear any existing handlers to avoid duplicates
    logger.handlers.clear()


    # 1. Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_formatter = coloredlogs.ColoredFormatter(
        fmt='%(asctime)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 2. Script-specific log file
    script_log_file = logs_dir / f"{script_name}.log"
    script_file_handler = logging.handlers.RotatingFileHandler(
        script_log_file,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    script_file_handler.setLevel(numeric_level)
    script_file_handler.setFormatter(jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s %(lineno)d %(pathname)s'
    ))
    logger.addHandler(script_file_handler)

    # 3. Combined script errors log
    script_errors_file = logs_dir / "script_errors.log"
    script_error_handler = logging.handlers.RotatingFileHandler(
        script_errors_file,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=5,
        encoding='utf-8'
    )
    script_error_handler.setLevel(logging.WARNING)
    script_error_handler.setFormatter(jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s %(lineno)d %(pathname)s'
    ))
    logger.addHandler(script_error_handler)

    # Add sanitization filter
    class SanitizeFilter(logging.Filter):
        def filter(self, record):
            record.msg = sanitize_log_message(str(record.msg))
            return True

    # Apply sanitization to all handlers
    for handler in logger.handlers:
        handler.addFilter(SanitizeFilter())

    logger.info("Script logging initialized for %s - Level: %s", script_name, log_level)
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def log_private_profile_detection(logger: logging.Logger, user_name: str, steam_id: str, operation: str):
    """
    Log private profile detection with consistent formatting.

    Args:
        logger: Logger instance
        user_name: Friendly name of the user
        steam_id: Steam ID of the user
        operation: Operation that failed (e.g., 'wishlist', 'library')
    """
    logger.warning("[PRIVATE_PROFILE] %s (%s): %s access blocked - profile is private", user_name, steam_id, operation)


def log_api_error(logger: logging.Logger, api_name: str, error: Exception, context: Optional[str] = None):
    """
    Log API errors with consistent formatting and context.

    Args:
        logger: Logger instance
        api_name: Name of the API (e.g., 'Steam Store', 'ITAD')
        error: Exception that occurred
        context: Additional context (e.g., user ID, app ID)
    """
    context_str = f" [{context}]" if context else ""
    logger.error("[API_ERROR] %s%s: %s: %s", api_name, context_str, type(error).__name__, error)


def log_rate_limit(logger: logging.Logger, api_name: str, backoff_time: float, reason: str = ""):
    """
    Log rate limiting events.

    Args:
        logger: Logger instance
        api_name: Name of the API being rate limited
        backoff_time: Time to wait before next request
        reason: Reason for rate limiting (optional)
    """
    reason_str = f" - {reason}" if reason else ""
    logger.warning("[RATE_LIMIT] %s: Backing off %.1fs%s", api_name, backoff_time, reason_str)


def log_performance_metric(logger: logging.Logger, operation: str, duration: float, count: int = 1):
    """
    Log performance metrics for operations.

    Args:
        logger: Logger instance
        operation: Name of the operation
        duration: Time taken in seconds
        count: Number of items processed
    """
    rate = count / duration if duration > 0 else 0
    logger.info("[PERFORMANCE] %s: %.2fs for %d items (%.1f/s)", operation, duration, count, rate)


# Create a default logger for immediate use
default_logger = logging.getLogger("familybot.default")

class _WebLogQueueHolder:
    """A singleton-like class to hold the web log queue."""
    def __init__(self):
        self.queue: Optional[Queue] = None

_web_log_queue_holder = _WebLogQueueHolder()

def get_web_log_queue():
    """Get the web log queue."""
    return _web_log_queue_holder.queue

def setup_web_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Set up logging for the web UI.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create web logger
    logger = logging.getLogger("familybot.web")
    logger.setLevel(numeric_level)
    logger.propagate = False

    # Clear any existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create web handler
    web_handler = WebSocketQueueHandler()
    web_handler.setLevel(numeric_level)
    _web_log_queue_holder.queue = web_handler.queue

    # Create formatter
    web_formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s %(lineno)d %(pathname)s'
    )
    web_handler.setFormatter(web_formatter)
    logger.addHandler(web_handler)

    logger.info("Web logging initialized - Level: %s", log_level)
    return logger
