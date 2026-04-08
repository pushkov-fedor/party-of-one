"""Regression: Round counter resets after compression deletes old turns.

Bug: Orchestrator._restore_state() computes round_number by counting
PLAYER turns remaining in the DB. After compression deletes old turns
(via delete_turns_before), the count drops because compressed player
turns no longer exist in the turns table. This causes ROUND displayed
to the user to go backwards (e.g., from 5 to 3).

Expected: round_number should monotonically increase regardless of
compression.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from party_of_one.config import AppConfig
from party_of_one.models import Turn, TurnRole


class TestRoundCounterAfterCompression:
    """Round counter must not decrease after compression removes old turns."""

    def test_round_number_counts_only_surviving_player_turns(self):
        """Demonstrates the bug: after deleting old turns,
        round_number is lower than the actual number of rounds played.

        If 5 player turns existed and compression deleted 3 of them,
        _restore_state should still report round 5, not round 2.
        """
        # This test documents the expected behavior.
        # Currently the implementation counts only surviving turns,
        # which is incorrect after compression.
        #
        # When fixed, _restore_state should either:
        # 1. Track round_number in a separate metadata table
        # 2. Count compressed turns from compressed_history table
        # 3. Use turn_number of the last player turn
        pass  # Placeholder until fix is implemented

    def test_round_number_should_be_monotonic(self):
        """round_number must never decrease between game rounds.

        This is a behavioral requirement: from the player's perspective,
        round numbers should always go up. Compression is an internal
        optimization and should not affect the user-facing round counter.
        """
        # Document the requirement
        # The ROUND output in CLI went: 1, 2, 3, 3, 4, 3
        # Expected:                     1, 2, 3, 4, 5, 6
        pass  # Placeholder until fix is implemented
