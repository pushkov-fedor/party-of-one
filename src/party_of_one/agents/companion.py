"""Companion Agent — AI-controlled party member with personality. Free text output."""

from __future__ import annotations

from pathlib import Path

import yaml

from contracts.companion import CompanionAgent as CompanionAgentContract

from party_of_one.agents.llm_client import call_with_retry, create_openrouter_client
from party_of_one.config import LLMConfig
from party_of_one.logger import get_logger
from party_of_one.models import (
    Character,
    CompanionPersonality,
    CompanionProfile,
    Turn,
)
from party_of_one.prompts import get_prompt

logger = get_logger()


def load_companion_profiles(path: str | Path) -> list[CompanionProfile]:
    """Load companion profiles from YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Companion profiles not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    profiles = []
    for c in data.get("companions", []):
        p = c.get("personality", {})
        profiles.append(CompanionProfile(
            name=c["name"],
            class_=c["class"],
            personality=CompanionPersonality(
                traits=p.get("traits", []),
                goals=p.get("goals", []),
                fears=p.get("fears", []),
                speaking_style=p.get("speaking_style", ""),
            ),
        ))
    return profiles


class CompanionAgent(CompanionAgentContract):
    """Companion agent — generates free text action based on personality."""

    PROMPT_VERSION = "companion-v2"

    def __init__(self, config: LLMConfig, profile: CompanionProfile):
        self.config = config
        self.profile = profile
        self.client = create_openrouter_client()

    def generate_action(
        self,
        *,
        profile: CompanionProfile,
        character: Character,
        world_state_snapshot: str,
        compressed_history: str = "",
        recent_turns: list[Turn] | None = None,
    ) -> str:
        """Generate companion's action as free text in first person."""
        history_parts = []
        if compressed_history:
            history_parts.append(f"## Сжатая история\n{compressed_history}")

        # Extract this companion's last action for anti-repetition
        last_action = ""
        if recent_turns:
            role_value = None
            for i, agent in enumerate(["companion_a", "companion_b"]):
                # Match by name in turn content
                if profile.name in str(recent_turns):
                    role_value = agent
                    break
            for t in reversed(recent_turns):
                if t.role.value in ("companion_a", "companion_b") and profile.name in t.content:
                    last_action = t.content
                    break

            turns_text = "\n".join(
                f"[{t.role.value}]: {t.content}" for t in recent_turns
            )
            history_parts.append(f"## Последние ходы\n{turns_text}")

        if last_action:
            history_parts.append(
                f"## Твоё предыдущее действие (НЕ ПОВТОРЯЙ)\n{last_action}"
            )

        history_section = "\n\n".join(history_parts)

        prompt = get_prompt("companion").format(
            name=profile.name,
            class_=profile.class_,
            traits="; ".join(profile.personality.traits),
            goals="; ".join(profile.personality.goals),
            fears="; ".join(profile.personality.fears),
            speaking_style=profile.personality.speaking_style,
            world_state_snapshot=world_state_snapshot,
            history_section=history_section,
        )

        messages = [{"role": "user", "content": prompt}]
        response = call_with_retry(
            self.client,
            model=self.config.model_companion,
            messages=messages,
            temperature=self.config.temperature_companion,
            max_tokens=self.config.max_tokens_companion,
            timeout=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
            agent_name="companion",
        )
        text = response.choices[0].message.content or ""
        return text.strip() or f"*{profile.name} выжидает.*"
