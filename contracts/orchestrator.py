"""Party of One — API Contract: Orchestrator.

Generated from specs in docs/specs/. Do not edit manually.
"""

from __future__ import annotations

from contracts.models import *

# 8. Orchestrator


@dataclass
class RoundResult:
    """Outcome of a single game round.

    In normal mode: player + companions. In watch mode: companions only.
    """

    round_number: int
    turns: list[Turn]
    dm_responses: list[DMResponse]
    actor_roles: list[TurnRole]  # who acted: player, companion_a, companion_b
    companion_texts: dict[str, str]  # actor_role.value -> companion's first-person text
    session_ended: bool
    end_reason: str | None = None  # "tpk" | "player_exit" | "critical_error"


@runtime_checkable
class Orchestrator(Protocol):
    """Deterministic turn manager and agent coordinator.

    The Orchestrator does NOT make game decisions. It routes actions,
    assembles context, enforces turn order, applies guardrails,
    and checks stop conditions.

    Turn order per round (normal mode):
        1. Player action  -> DM processes -> narrative
        2. Companion A    -> DM processes -> narrative
        3. Companion B    -> DM processes -> narrative

    Turn order per round (watch mode, ``process_watch_round``):
        1. Companion A    -> DM processes -> narrative
        2. Companion B    -> DM processes -> narrative

    A companion's turn is skipped if its status is ``dead``,
    ``incapacitated``, ``paralyzed``, or ``delirious``.

    State transitions (normal):
        awaiting_player -> processing_player_turn -> awaiting_companion_a
        -> processing_companion_a_turn -> awaiting_companion_b
        -> processing_companion_b_turn -> round_complete -> awaiting_player

    State transitions (watch):
        awaiting_player -> awaiting_companion_a
        -> processing_companion_a_turn -> awaiting_companion_b
        -> processing_companion_b_turn -> round_complete -> awaiting_player

    Stop conditions:
        - TPK (Total Party Kill): all party members HP <= 0.
        - Player exit (``/quit``).
        - Critical error: 3 consecutive LLM failures.
    """

    def init_game(
        self,
        *,
        player_archetype: str,
        companion_choices: list[str],
        setting_description: str,
        player_name: str = "Hero",
    ) -> DMResponse:
        """Initialize a new game session.

        Steps:
        1. Create the player character (roll 3d6 for STR/DEX/WIL,
           1d6 for HP via ``roll_dice``).
        2. Create the two chosen companions in World State.
        3. Create a placeholder starting location.
        4. Call ``DMAgent.generate_init()`` for opening narrative
           and setup tool calls (NPCs, quest, equipment, location detail).
        5. Execute the DM's tool calls via ``ToolExecutor``.
        6. Transition to ``awaiting_player``.

        Args:
            player_archetype: E.g. ``"Warrior"``, ``"Scout"``, ``"Mage"``,
                ``"Rogue"``.
            companion_choices: Two companion names matching profiles in
                ``data/companions.yaml``.
            setting_description: Free-form setting description from player.

        Returns:
            The ``DMResponse`` containing the opening narrative.

        Raises:
            ValueError: If *player_archetype* is empty, or
                *companion_choices* length != 2, or names
                don't match available profiles.
            RuntimeError: If the DM init call fails after retries.
        """
        ...

    def process_round(
        self,
        player_action: str,
    ) -> RoundResult:
        """Process one full game round.

        For each actor in turn order:
        1. Run pre-LLM guardrail on input (skipped in watch mode).
        2. Build context: snapshot, compressed history, recent turns, RAG.
        3. Call the appropriate agent (DM or Companion).
        4. Run post-LLM guardrail on output.
        5. Validate and execute tool calls (DM turns only).
        6. Save the turn to the database.
        7. Check stop conditions (TPK, etc.).
        8. Trigger compression if the working context exceeds
           ``compression_threshold_tokens``.

        If a DM response is blocked by the post-LLM guardrail, re-prompt
        up to ``max_retries_on_block`` times. If a tool call is invalid,
        re-prompt with the validation error (up to 2 times). Ultimate
        fallback: accept narrative without tool calls (world not updated,
        turn still counted).

        Args:
            player_action: The player's declared action text. In watch
                mode, this is the default ``"observes"`` string.

        Returns:
            ``RoundResult`` with all turns, DM responses, and whether
            the session ended.

        Raises:
            RuntimeError: Only on truly unrecoverable errors (e.g. DB
                corruption).  Normal LLM failures are handled internally
                via retry/fallback and reported in ``RoundResult``.
        """
        ...

    def process_watch_round(self) -> RoundResult:
        """Process one watch-mode round (companions only, no player turn).

        For each alive companion in turn order:
        1. Generate companion action via CompanionAgent.
        2. Send to DM Agent for processing and narrative.
        3. Run post-LLM guardrail on DM output.
        4. Validate and execute tool calls.
        5. Save turns to database.
        6. Check stop conditions (TPK).
        7. Trigger compression if threshold exceeded.

        No player action is processed. No pre-LLM guardrail is run.
        ``actor_roles`` in the result will only contain companion roles.

        Returns:
            ``RoundResult`` with companion turns only.

        Raises:
            RuntimeError: Only on truly unrecoverable errors.
        """
        ...
