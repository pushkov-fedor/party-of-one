"""Phase 0: Logger tests.

Tests behavior described in docs/specs/serving-config.md (Logging section):
- Logger writes JSONL format to a file
- Each log entry contains timestamp, event, and level fields
"""

import json
import tempfile
from pathlib import Path

import pytest

from party_of_one.logger import get_logger, setup_logging


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def log_file(tmp_path):
    """Provide a temporary log file path."""
    return tmp_path / "test.jsonl"


@pytest.fixture
def logger(log_file):
    """Set up logging to a temp file and return a logger instance."""
    setup_logging(log_file=str(log_file), level="DEBUG")
    return get_logger(component="test")


# ---------------------------------------------------------------------------
# JSONL file output
# ---------------------------------------------------------------------------

class TestLoggerWritesJSONL:
    """Logger writes structured JSONL (one JSON object per line) to the configured file."""

    def test_log_file_created_after_write(self, logger, log_file):
        logger.info("test_event")
        assert log_file.exists()

    def test_each_line_is_valid_json(self, logger, log_file):
        logger.info("event_one")
        logger.info("event_two")
        lines = [l for l in log_file.read_text().strip().splitlines() if l.strip()]
        assert len(lines) >= 2
        for line in lines:
            parsed = json.loads(line)  # should not raise
            assert isinstance(parsed, dict)

    def test_multiple_log_entries_append(self, logger, log_file):
        logger.info("first")
        logger.warning("second")
        logger.error("third")
        lines = [l for l in log_file.read_text().strip().splitlines() if l.strip()]
        assert len(lines) >= 3


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

class TestLogEntryContainsRequiredFields:
    """Each JSONL log entry must contain at least: timestamp, event, level."""

    def test_entry_has_timestamp(self, logger, log_file):
        logger.info("check_fields")
        lines = [l for l in log_file.read_text().strip().splitlines() if l.strip()]
        entry = json.loads(lines[-1])
        assert "timestamp" in entry or "ts" in entry or any(
            "time" in k.lower() for k in entry
        ), f"No timestamp field found in {entry.keys()}"

    def test_entry_has_event(self, logger, log_file):
        logger.info("my_event")
        lines = [l for l in log_file.read_text().strip().splitlines() if l.strip()]
        entry = json.loads(lines[-1])
        assert "event" in entry, f"No 'event' field in {entry.keys()}"

    def test_entry_has_level(self, logger, log_file):
        logger.warning("level_check")
        lines = [l for l in log_file.read_text().strip().splitlines() if l.strip()]
        entry = json.loads(lines[-1])
        assert "level" in entry or "log_level" in entry, (
            f"No level field found in {entry.keys()}"
        )

    def test_event_matches_logged_message(self, logger, log_file):
        logger.info("specific_event_name")
        lines = [l for l in log_file.read_text().strip().splitlines() if l.strip()]
        entry = json.loads(lines[-1])
        assert entry.get("event") == "specific_event_name"

    def test_level_reflects_severity(self, logger, log_file):
        logger.error("error_event")
        lines = [l for l in log_file.read_text().strip().splitlines() if l.strip()]
        entry = json.loads(lines[-1])
        level_field = entry.get("level") or entry.get("log_level", "")
        assert "error" in level_field.lower()
