"""Regression: HistoryCompressor instantiation with keyword-only db parameter.

Bug: Orchestrator.__init__() passed db as a positional argument to
HistoryCompressor(config, self.db), but HistoryCompressor.__init__
declares db as keyword-only (after *). This caused TypeError on every
new game creation.

Fix: Changed call to HistoryCompressor(config, db=self.db).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from party_of_one.config import AppConfig
from party_of_one.memory.compressor import HistoryCompressor


class TestHistoryCompressorInstantiation:
    """Verify HistoryCompressor can be created with config + db as keyword."""

    def test_create_with_config_and_db_keyword(self):
        """db must be passed as keyword argument -- the crash scenario."""
        config = AppConfig()
        mock_db = MagicMock()
        # This should NOT raise TypeError
        compressor = HistoryCompressor(config, db=mock_db)
        assert compressor.config is config
        assert compressor.db is mock_db

    def test_create_with_positional_db_raises(self):
        """Passing db positionally must raise TypeError (keyword-only param)."""
        config = AppConfig()
        mock_db = MagicMock()
        with pytest.raises(TypeError):
            HistoryCompressor(config, mock_db)  # type: ignore[misc]

    def test_create_without_config(self):
        """Config is optional, db is required keyword."""
        mock_db = MagicMock()
        compressor = HistoryCompressor(db=mock_db)
        assert compressor.db is mock_db
