"""Structured JSON logging via structlog."""

from __future__ import annotations

import sys
from pathlib import Path

import structlog


def setup_logging(log_file: str = "./logs/session.jsonl", level: str = "INFO") -> None:
    """Configure structlog to output JSON Lines to file and stderr."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = open(log_path, "a")  # noqa: SIM115

    def write_to_file(_, __, event_dict: dict) -> dict:
        """Processor that writes each log entry to the JSONL file."""
        import json

        line = json.dumps(event_dict, ensure_ascii=False, default=str)
        file_handler.write(line + "\n")
        file_handler.flush()
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            write_to_file,
            structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(structlog._log_levels._NAME_TO_LEVEL[level.lower()]),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(**kwargs) -> structlog.stdlib.BoundLogger:
    """Get a logger with optional bound context (agent, turn, round, etc.)."""
    return structlog.get_logger(**kwargs)
