"""
Structured logging configuration for SOLAT trading engine.

Provides consistent logging format across all modules with:
- JSON structured output for production
- Human-readable output for development
- Automatic redaction of sensitive fields
- Run ID tracking for audit trails
"""

import logging
import sys
from collections import deque
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variable for tracking run IDs across async operations
current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)

# Fields that should be redacted in logs
REDACTED_FIELDS = {
    "password",
    "api_key",
    "apikey",
    "secret",
    "token",
    "authorization",
    "auth",
    "credential",
    "private_key",
}


def redact_sensitive(data: Any, depth: int = 0) -> Any:
    """
    Recursively redact sensitive fields from data structures.

    Args:
        data: Data to redact (dict, list, or scalar)
        depth: Current recursion depth (prevents infinite recursion)

    Returns:
        Data with sensitive fields replaced with "[REDACTED]"
    """
    if depth > 10:
        return data

    if isinstance(data, dict):
        return {
            k: (
                "[REDACTED]"
                if any(redact in k.lower() for redact in REDACTED_FIELDS)
                else redact_sensitive(v, depth + 1)
            )
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [redact_sensitive(item, depth + 1) for item in data]
    return data


class SOLATFormatter(logging.Formatter):
    """
    Custom formatter for SOLAT logs.

    Includes timestamp, level, module, run_id (if set), and message.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Add timestamp in ISO format
        record.timestamp = datetime.now(UTC).isoformat()

        # Add run_id if available
        run_id = current_run_id.get()
        record.run_id = f"[{run_id}] " if run_id else ""

        # Format the message
        return super().format(record)


class InMemoryHandler(logging.Handler):
    """In-memory log handler for UI diagnostics."""

    def __init__(self, capacity: int = 1000):
        super().__init__()
        self.logs: deque[dict[str, Any]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # We don't use the formatter here to keep raw message + extra
            log_entry = {
                "timestamp": getattr(record, "timestamp", datetime.now(UTC).isoformat()),
                "level": record.levelname,
                "level_no": record.levelno,
                "logger": record.name,
                "message": record.getMessage(),
                "extra": redact_sensitive(getattr(record, "args", {}) if isinstance(record.args, dict) else {}),
            }
            self.logs.append(log_entry)
        except Exception:
            self.handleError(record)


_in_memory_handler = InMemoryHandler()


def setup_logging(level: str = "INFO", json_output: bool = False) -> logging.Logger:
    """
    Configure logging for the SOLAT engine.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output JSON format (for production)

    Returns:
        Configured root logger
    """
    # Clear any existing handlers
    root = logging.getLogger()
    root.handlers.clear()

    # Set level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)

    # Create stream handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    # Set format based on environment
    if json_output:
        # JSON format for production/parsing
        fmt = (
            '{"timestamp": "%(timestamp)s", "level": "%(levelname)s", '
            '"module": "%(name)s", "run_id": "%(run_id)s", "message": "%(message)s"}'
        )
    else:
        # Human-readable format for development
        fmt = "%(timestamp)s | %(levelname)-8s | %(name)s | %(run_id)s%(message)s"

    formatter = SOLATFormatter(fmt)
    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Add in-memory handler
    _in_memory_handler.setLevel(numeric_level)
    _in_memory_handler.setFormatter(formatter)
    root.addHandler(_in_memory_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    return root


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def get_in_memory_logs(level: str = "INFO", limit: int = 50) -> list[dict[str, Any]]:
    """Get filtered logs from memory."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    filtered = [log for log in _in_memory_handler.logs if log["level_no"] >= numeric_level]
    return filtered[-limit:]


def set_run_id(run_id: str) -> None:
    """Set the current run ID for log correlation."""
    current_run_id.set(run_id)


def clear_run_id() -> None:
    """Clear the current run ID."""
    current_run_id.set(None)
