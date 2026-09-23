"""Structured JSON logging.

Locally this just prints readable JSON lines to stdout. The point is what
happens once this runs in ECS: the awslogs driver ships whatever a
container writes to stdout straight to CloudWatch Logs, no code changes
needed. Because the lines are already JSON, CloudWatch Logs Insights can
query on fields directly later (e.g. count of `backtest_failed` events by
`strategy` in the last hour) instead of regex-parsing free text.
"""

from __future__ import annotations

import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_event(logger: logging.Logger, level: int, message: str, **fields) -> None:
    """Log `message` with `fields` merged into the JSON payload as
    top-level keys, e.g. log_event(logger, logging.INFO, "backtest_started",
    run_id=run_id, ticker="AAPL") -> {"message": "backtest_started",
    "run_id": "...", "ticker": "AAPL", ...}.
    """
    logger.log(level, message, extra={"extra_fields": fields})
