"""Shared helpers: structured logging, timing, and retry defaults."""

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone

logger = logging.getLogger("research-agent")
logger.setLevel(logging.INFO)


def log_structured(level: str, message: str, **kwargs) -> None:
    """Emit a single-line JSON log entry (CloudWatch-friendly)."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        **kwargs,
    }
    getattr(logger, level.lower(), logger.info)(json.dumps(entry))


@contextmanager
def timed(label: str):
    """Context manager that logs elapsed wall-clock seconds."""
    start = time.monotonic()
    yield
    elapsed = round(time.monotonic() - start, 2)
    log_structured("INFO", f"{label} completed", elapsed_seconds=elapsed)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
