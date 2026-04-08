"""Party of One — API Contract: Dm Agent.

Generated from specs in docs/specs/. Do not edit manually.
"""

from __future__ import annotations

from contracts.models import *

# 6. DM Agent


@dataclass
class DMResponse:
    """The complete output of a DM Agent LLM call."""

    narrative: str
    """Flavour text for the player (max ~500 tokens)."""

    tool_calls: list[dict[str, Any]]
    """Structured tool-call requests extracted via function-calling."""


@runtime_checkable
class DMAgent(Protocol):
    """DM Agent -- the primary narrative LLM agent.

    Describes the world, manages NPCs, resolves player and companion
    actions, applies Cairn rules, and updates World State via tool calls.
    """

    def generate(
        self,
        *,
        action: str,
        actor_role: TurnRole,
        world_state_snapshot: str,
        compressed_history: str,
        recent_turns: list[Turn],
        rag_results: str,
    ) -> DMResponse:
        """Generate DM narrative + tool calls in response to an action.

        Assembles the full prompt from the provided context fragments
        and calls the LLM with function-calling enabled.

        Args:
            action: The player's or companion's declared action text.
            actor_role: Who is acting (player / companion_a / companion_b).
            world_state_snapshot: Textual snapshot from
                ``WorldStateDB.snapshot()``.
            compressed_history: Compressed past events summary.
            recent_turns: The N most recent raw turns.
            rag_results: Relevant Cairn SRD excerpts (may be empty).

        Returns:
            ``DMResponse`` containing narrative text and tool calls.

        Raises:
            TimeoutError: If the LLM call exceeds the configured timeout
                after all retries.
            RuntimeError: If the LLM returns an unparseable response
                after retry attempts.

        Invariants:
            - Narrative length <= 500 tokens.
            - If the action involves mechanics (attack, save, check),
              at least one ``roll_dice`` tool call MUST be present.
            - Temperature: 0.7-0.8.
        """
        ...

    def generate_init(
        self,
        *,
        setting_description: str,
        player_character: Character,
        companion_profiles: list[CompanionProfile],
        world_state_snapshot: str,
    ) -> DMResponse:
        """Generate the opening scene for a new game.

        The DM is instructed to:
        - Create the initial narrative
        - Create 1-3 NPCs via ``create_character``
        - Create a starting quest via ``create_quest``
        - Assign starting equipment via ``add_item`` (per Cairn rules)
        - Fill in the starting location description via ``update_location``

        Args:
            setting_description: Free-form setting description from player.
            player_character: The player's character (already in DB).
            companion_profiles: Selected companion profiles.
            world_state_snapshot: Current world state (minimal at init).

        Returns:
            ``DMResponse`` with opening narrative and setup tool calls.

        Raises:
            TimeoutError: If the LLM call exceeds timeout after retries.
            RuntimeError: If the response is unparseable after retries.
        """
        ...
