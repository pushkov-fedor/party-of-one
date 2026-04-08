"""Party of One — API Contract: Tools.

Generated from specs in docs/specs/. Do not edit manually.
"""

from __future__ import annotations

from contracts.models import *

# 5. ToolExecutor


class ToolExecutor(ABC):
    """Validates and executes DM tool calls against the WorldStateDB.

    All commands from a single DM turn are executed inside one SQLite
    transaction.  If ANY command fails validation, the entire batch is
    rolled back and the DM receives a re-prompt with the error details.

    Invariants:
        - Maximum 10 tool calls per turn.
        - Maximum damage per single call: 50.
        - Maximum armor: 3.
        - Maximum inventory slots: 10.
    """

    @abstractmethod
    def execute(self, tool_name: str, params: dict[str, Any]) -> ToolCallResult:
        """Execute a single DM tool call.

        Performs three-stage validation:
        1. Schema validation -- params match the tool's JSON schema.
        2. Referential integrity -- all entity IDs exist.
        3. Business rules -- dead characters can't move, HP can't exceed
           max, etc.

        Args:
            tool_name: Name of the tool (e.g. ``"damage_character"``,
                ``"roll_dice"``).
            params: Tool-specific parameters.

        Returns:
            ``ToolCallResult`` with success/failure and result or error.

        Raises:
            ValueError: If *tool_name* is unknown.
        """
        ...

    @abstractmethod
    def execute_batch(
        self, calls: list[dict[str, Any]]
    ) -> list[ToolCallResult]:
        """Execute a batch of tool calls from one DM turn atomically.

        All write operations share a single SQLite transaction.
        Read-only calls (``roll_dice``, ``get_entity``) are executed
        outside the transaction.

        Args:
            calls: List of dicts, each with ``"name"`` and ``"params"`` keys.
                Maximum length: 10.

        Returns:
            List of ``ToolCallResult``, one per call, in order.

        Raises:
            ValueError: If *calls* has more than 10 entries.
            RuntimeError: If any write call fails validation -- the entire
                transaction is rolled back and all results will have
                ``success=False``.
        """
        ...
