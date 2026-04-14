"""DM Agent — narrative generation via LLM with tool use."""

from __future__ import annotations

import json

from contracts.dm_agent import DMAgent as DMAgentContract

from party_of_one.agents.llm_client import call_with_retry, create_openrouter_client
from party_of_one.config import LLMConfig
from party_of_one.logger import get_logger
from party_of_one.models import (
    Character,
    CompanionProfile,
    DMResponse,
    Turn,
    TurnRole,
)
from party_of_one.prompts import get_prompt
from party_of_one.tools.tool_definitions import TOOL_DEFINITIONS

logger = get_logger()


class DMAgent(DMAgentContract):
    """DM Agent — calls LLM with tool definitions, parses response."""

    def __init__(self, config: LLMConfig, tool_executor=None, extra_body: dict | None = None):
        self.config = config
        self.tool_executor = tool_executor
        self._current_max_tokens = config.max_tokens_dm
        self._extra_body = extra_body
        self.client = create_openrouter_client()

    def generate(
        self,
        *,
        action: str,
        actor_role: TurnRole,
        world_state_snapshot: str,
        compressed_history: str,
        recent_turns: list[Turn],
        rag_results: str = "",
    ) -> DMResponse:
        """Generate DM narrative + tool calls in response to an action."""
        self._current_max_tokens = self.config.max_tokens_dm

        rag_section = f"## Relevant Cairn Rules\n{rag_results}" if rag_results else ""

        history_parts = []
        if compressed_history:
            history_parts.append(f"## Compressed History\n{compressed_history}")
        if recent_turns:
            turns_text = "\n".join(self._format_turn(t) for t in recent_turns)
            history_parts.append(f"## Recent Turns\n{turns_text}")
        history_section = "\n\n".join(history_parts)

        prompt = get_prompt("dm_system").format(
            world_state_snapshot=world_state_snapshot,
            rag_section=rag_section,
            history_section=history_section,
            current_action=action,
        )
        messages = [{"role": "user", "content": prompt}]
        return self._tool_use_loop(messages)

    def generate_init(
        self,
        *,
        setting_description: str,
        player_character: Character,
        companion_profiles: list[CompanionProfile],
        world_state_snapshot: str,
    ) -> DMResponse:
        """Generate the opening scene for a new game."""
        self._current_max_tokens = 4096

        party_lines = [
            f"- {player_character.name} [id: {player_character.id}] ({player_character.class_}): "
            f"STR {player_character.strength}, DEX {player_character.dexterity}, "
            f"WIL {player_character.willpower}, HP {player_character.hp}"
        ]
        for p in companion_profiles:
            party_lines.append(f"- {p.name} ({p.class_})")

        prompt = get_prompt("dm_init").format(
            setting_description=setting_description,
            party_description="\n".join(party_lines),
            world_state_snapshot=world_state_snapshot,
        )
        messages = [{"role": "user", "content": prompt}]
        return self._tool_use_loop(messages)

    _RETRY_MSG = "Ты не дал ответа. Опиши что происходит в мире — 2-4 предложения."

    def _tool_use_loop(self, messages: list[dict], max_rounds: int = 20) -> DMResponse:
        all_tool_calls: list[dict] = []
        empty_retries = 0
        max_empty_retries = 3

        for _ in range(max_rounds):
            response = call_with_retry(
                self.client, model=self.config.model, messages=messages,
                temperature=self.config.temperature_dm,
                max_tokens=self._current_max_tokens,
                timeout=self.config.timeout_seconds,
                max_retries=self.config.max_retries, agent_name="dm",
                tools=TOOL_DEFINITIONS,
                extra_body=self._extra_body,
            )
            parsed = self._parse_response(response)

            if parsed.tool_calls and self.tool_executor:
                all_tool_calls.extend(parsed.tool_calls)
                messages.append(response.choices[0].message.model_dump())
                for tc in parsed.tool_calls:
                    try:
                        result = self.tool_executor.execute(tc["name"], tc["args"])
                        result_str = json.dumps(result.result, ensure_ascii=False, default=str)
                    except (ValueError, RuntimeError) as e:
                        result_str = json.dumps({"error": str(e)}, ensure_ascii=False)
                        logger.warning("tool_error_in_loop", tool=tc["name"], error=str(e))
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})
                continue

            # Empty narrative — retry instead of returning silence
            if not parsed.narrative or not parsed.narrative.strip():
                empty_retries += 1
                if empty_retries <= max_empty_retries:
                    logger.warning("dm_empty_narrative_retry", attempt=empty_retries)
                    messages.append({"role": "user", "content": self._RETRY_MSG})
                    continue
                # Exhausted retries — return fallback
                logger.warning("dm_empty_narrative_fallback", attempts=empty_retries)
                parsed.narrative = "*Тишина повисает в воздухе...*"

            parsed.tool_calls = all_tool_calls
            return parsed

        logger.warning("tool_use_loop_max_rounds", rounds=max_rounds)
        return DMResponse(narrative="*Тишина повисает в воздухе...*", tool_calls=all_tool_calls)

    def _parse_response(self, response) -> DMResponse:
        message = response.choices[0].message
        narrative = message.content or ""
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    logger.error("tool_call_parse_error", raw=tc.function.arguments)
                    continue
                tool_calls.append({"id": tc.id, "name": tc.function.name, "args": args})
        return DMResponse(narrative=narrative, tool_calls=tool_calls)

    @staticmethod
    def _format_turn(turn: Turn) -> str:
        labels = {"player": "Player", "dm": "DM", "companion_a": "Companion A", "companion_b": "Companion B"}
        role_str = turn.role.value if hasattr(turn.role, "value") else turn.role
        return f"[{labels.get(role_str, role_str)}]: {turn.content}"
