"""Post-LLM Guardrail — checks DM response for leaks and validates commands."""

from __future__ import annotations

from typing import Any

from contracts.guardrails import (
    GuardrailResult,
    PostLLMGuardrail as PostLLMGuardrailContract,
    PostLLMResult,
)

from party_of_one.config import GuardrailsConfig
from party_of_one.logger import get_logger
from party_of_one.tools.tool_definitions import TOOL_DEFINITIONS

logger = get_logger()

# Phrases from system prompt that should never appear in DM output
_LEAK_PHRASES: list[str] = [
    # Russian (from system prompt)
    "Ты — Dungeon Master",
    "НИКОГДА не выходи из роли",
    "КРИТИЧЕСКИЕ ПРАВИЛА",
    "ВРАГИ ДЕЙСТВУЮТ",
    "NPC — ЖИВЫЕ ЛЮДИ",
    # Bracket and bare forms
    "[prompt_version:",
    "prompt_version:",
    "prompt_version",
    # English translations (against translation attacks)
    "never break character",
    "critical rules",
    "enemies act",
    # Meta-commentary: tool call names leaked into narrative
    "tool call",
    "tool_call",
    "damage_character",
    "roll_dice",
    "create_character",
    "update_character",
    "move_entity",
    "search_rules",
    "add_item",
    "remove_item",
    "add_fatigue",
    "heal_character",
    # Meta-commentary: DM planning/reasoning
    "техническая пауза",
    "в состоянии мира",
    "не требует tool",
    "по правилам cairn",
    # Meta-commentary: dice notation and stats in narrative
    "спасбросок str",
    "спасбросок dex",
    "спасбросок wil",
    "hp падает",
    "hp обновлён",
    "бросок d",
    "d20 =",
    "d6=",
    "d8=",
    "d4=",
    "d10=",
    "d12=",
    "я бросаю",
    "я провожу",
    "боевых действий не происходит",
    "перемещён в loc_",
    "перемещён в новую локацию",
]

# Build schema lookup from tool definitions
_TOOL_SCHEMAS: dict[str, dict] = {}
for _td in TOOL_DEFINITIONS:
    _func = _td["function"]
    _TOOL_SCHEMAS[_func["name"]] = _func.get("parameters", {})


class PostLLMGuardrail(PostLLMGuardrailContract):
    """Leak detection + command validation before execution."""

    def __init__(self, config: GuardrailsConfig | None = None, db=None):
        self.config = config or GuardrailsConfig()
        self.db = db

    def check_narrative(self, narrative: str) -> GuardrailResult:
        if not self.config.post_llm_enabled:
            return GuardrailResult(passed=True)

        narrative_lower = narrative.lower()
        for phrase in _LEAK_PHRASES:
            if phrase.lower() in narrative_lower:
                reason = f"leak_detected: '{phrase}'"
                logger.warning("post_llm_leak", reason=reason,
                               narrative_preview=narrative[:200])
                return GuardrailResult(passed=False, reason=reason)

        return GuardrailResult(passed=True)

    def validate_commands(
        self, commands: list[dict[str, Any]],
    ) -> PostLLMResult:
        if not self.config.post_llm_enabled:
            return PostLLMResult(passed=True)

        if not commands:
            return PostLLMResult(passed=True)

        invalid: list[str] = []

        for cmd in commands:
            name = cmd.get("name", "")
            args = cmd.get("args", {})

            # 1. Schema validation
            schema = _TOOL_SCHEMAS.get(name)
            if schema is None:
                invalid.append(f"unknown tool: {name}")
                continue

            required = schema.get("required", [])
            properties = schema.get("properties", {})
            for req in required:
                if req not in args:
                    invalid.append(f"{name}: missing required param '{req}'")

            for param_name, param_value in args.items():
                if param_name in properties:
                    prop = properties[param_name]
                    expected_type = prop.get("type")
                    if expected_type == "integer" and not isinstance(param_value, int):
                        invalid.append(f"{name}: param '{param_name}' should be integer")
                    if expected_type == "string" and not isinstance(param_value, str):
                        invalid.append(f"{name}: param '{param_name}' should be string")
                    if expected_type == "boolean" and not isinstance(param_value, bool):
                        invalid.append(f"{name}: param '{param_name}' should be boolean")
                    if "enum" in prop and param_value not in prop["enum"]:
                        invalid.append(
                            f"{name}: param '{param_name}' value '{param_value}' "
                            f"not in {prop['enum']}"
                        )

            # 2. Referential integrity
            if self.db:
                try:
                    self._check_refs(name, args)
                except KeyError as e:
                    invalid.append(f"{name}: {e}")

            # 3. Business rules
            biz_error = self._check_business_rules(name, args)
            if biz_error:
                invalid.append(f"{name}: {biz_error}")

        if invalid:
            logger.warning("post_llm_invalid_commands", errors=invalid)
            return PostLLMResult(
                passed=False,
                invalid_commands=invalid,
                reason=f"{len(invalid)} invalid command(s)",
            )

        return PostLLMResult(passed=True)

    def _check_refs(self, name: str, args: dict) -> None:
        if not self.db:
            return
        if "character_id" in args:
            self.db.characters.get(args["character_id"])
        if "entity_id" in args:
            self.db.characters.get(args["entity_id"])
        if "giver_character_id" in args:
            self.db.characters.get(args["giver_character_id"])
        if name == "move_entity" and "location_id" in args:
            self.db.locations.get(args["location_id"])
        if name == "update_location" and "location_id" in args:
            self.db.locations.get(args["location_id"])
        if "quest_id" in args:
            self.db.quests.get(args["quest_id"])
        if name == "get_entity":
            self.db.get_entity(args.get("type", ""), args.get("id", ""))
        if name == "create_location" and "connected_to" in args:
            for loc_id in args["connected_to"]:
                self.db.locations.get(loc_id)

    def _check_business_rules(self, name: str, args: dict) -> str | None:
        if not self.db:
            return None
        if name == "damage_character":
            amount = args.get("amount", 0)
            if amount < 1:
                return f"damage {amount} must be >= 1"
            char_id = args.get("character_id")
            if char_id:
                try:
                    char = self.db.characters.get(char_id)
                    if char.status.value in ("dead", "incapacitated"):
                        return f"cannot damage {char.status.value} character"
                except KeyError:
                    pass
        if name == "create_character":
            armor = args.get("armor", 0)
            if armor < 0 or armor > 3:
                return f"armor {armor} must be in [0, 3]"
        if name in ("damage_character", "heal_character", "damage_stat",
                     "restore_stat", "move_entity", "add_fatigue"):
            char_id = args.get("character_id") or args.get("entity_id")
            if char_id and self.db:
                try:
                    char = self.db.characters.get(char_id)
                    if name == "move_entity" and char.status.value == "dead":
                        return "cannot move dead character"
                    if name == "heal_character" and char.status.value == "deprived":
                        return "deprived character cannot heal"
                except KeyError:
                    pass
        return None


# Alias expected by tests
PostLLMGuardrailImpl = PostLLMGuardrail
