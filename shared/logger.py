# shared/logger.py
"""Structured JSON logger for CloudWatch Logs Insights.

CloudWatch Logs Insights can filter on fields like:
  fields @timestamp, event, story_hash, routing_decision, editorial_score
"""
import json
from datetime import datetime, timezone
from typing import Any


def log(level: str, event: str, **kwargs: Any) -> None:
    """Emit a structured JSON log line to stdout."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        **kwargs,
    }
    print(json.dumps(payload), flush=True)
