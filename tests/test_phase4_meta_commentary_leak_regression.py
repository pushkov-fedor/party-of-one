"""Regression: DM meta-commentary leak in narrative text.

Bug: When the DM encounters an error processing a companion action (e.g.,
damage_character targeting a non-character entity like a location ID), it
emits internal planning/debug commentary directly into the player-visible
narrative instead of handling it silently.

Observed leak pattern (round 5 of stress test, 2026-04-15):
  "(Техническая пауза: обнаружена ошибка в идентификаторе цели для урона.
   Бранка атакует стену/механизм ловушки, а не персонажа — урон по объекту
   не требует tool call damage_character, если это не NPC/монстр. В ответ
   враги не атакуют, т.к. только страж и послушник, и они парализованы
   страхом.)"

This violates the DM prompt rule that forbids showing dice numbers, rules
references, tool call names, and planning meta in the narrative output.

The PostLLMGuardrail.check_narrative() should catch meta-commentary patterns
like parenthetical system notes, tool call references, and technical pauses.
"""

from __future__ import annotations

import pytest

from party_of_one.guardrails.post_llm import PostLLMGuardrail


# ---------------------------------------------------------------------------
# The exact leaked text from the observed bug
# ---------------------------------------------------------------------------

LEAKED_NARRATIVE = (
    "(Техническая пауза: обнаружена ошибка в идентификаторе цели для урона. "
    "Бранка атакует стену/механизм ловушки, а не персонажа — урон по объекту "
    "не требует tool call damage_character, если это не NPC/монстр. В ответ "
    "враги не атакуют, т.к. только страж и послушник, и они парализованы страхом.)"
)

# Additional meta-commentary patterns that should be caught
META_COMMENTARY_PATTERNS = [
    "(Техническая пауза: проверяю состояние игрового мира)",
    "(Бросок d20 = 14, проверка STR пройдена)",
    "tool call damage_character не требуется",
    "(урон по объекту не требует tool call)",
    "(HP стража падает до 0, спасбросок STR провален)",
    "(боевых действий не происходит — все противники мертвы)",
    "Я бросаю кубик за Бранку и получаю 6",
    "(Тестер перемещён в loc_dungeon_hall)",
    "По правилам Cairn, спасбросок STR (14) пройден",
    "результат броска d6=5, урон 5",
]

# Clean narratives that should pass
CLEAN_NARRATIVES = [
    "Клинок воина настигает стража и с размахом рассеивает призрачную плоть.",
    "Бранка со звериной яростью бросается вперёд, и её топор с глухим хрустом рассекает кости стража.",
    "Тихомир внимательно осматривает землю у ворот, ощупывает каждый камень.",
    "Тестер быстро достаёт целебное зелье и аккуратно вливает его в рот Тихомиру.",
]


class TestMetaCommentaryLeakDetection:
    """PostLLMGuardrail.check_narrative must catch DM meta-commentary leaks."""

    @pytest.fixture
    def guardrail(self):
        return PostLLMGuardrail()

    def test_exact_observed_leak_is_caught(self, guardrail):
        """The exact leaked text observed in the game session must be blocked."""
        result = guardrail.check_narrative(LEAKED_NARRATIVE)
        assert not result.passed, (
            f"Meta-commentary leak was NOT caught by check_narrative. "
            f"Leaked text: {LEAKED_NARRATIVE!r}"
        )

    @pytest.mark.parametrize("meta_text", META_COMMENTARY_PATTERNS)
    def test_meta_commentary_patterns_are_caught(self, guardrail, meta_text):
        """Various meta-commentary patterns must be blocked."""
        result = guardrail.check_narrative(meta_text)
        assert not result.passed, (
            f"Meta-commentary pattern was NOT caught: {meta_text!r}"
        )

    def test_meta_commentary_embedded_in_clean_narrative(self, guardrail):
        """Meta-commentary embedded within otherwise clean narrative must be caught."""
        narrative_with_leak = (
            "Бранка с яростью обрушивает топор на камень — острое лезвие "
            "с глухим треском дробит плиты. "
            "(Техническая пауза: обнаружена ошибка в идентификаторе цели для урона.) "
            "Пыль и мелкие обломки разлетаются по двору."
        )
        result = guardrail.check_narrative(narrative_with_leak)
        assert not result.passed, (
            "Meta-commentary embedded in clean narrative was NOT caught"
        )

    @pytest.mark.parametrize("clean_text", CLEAN_NARRATIVES)
    def test_clean_narratives_pass(self, guardrail, clean_text):
        """Clean narrative text without meta-commentary must pass."""
        result = guardrail.check_narrative(clean_text)
        assert result.passed, (
            f"Clean narrative was incorrectly blocked: {clean_text!r}, "
            f"reason: {result.reason}"
        )

    def test_tool_call_reference_in_narrative(self, guardrail):
        """References to tool call names in narrative must be blocked."""
        narrative = "Урон не применён, т.к. damage_character вернул ошибку."
        result = guardrail.check_narrative(narrative)
        assert not result.passed, (
            "Tool call name 'damage_character' in narrative was NOT caught"
        )

    def test_parenthetical_system_note(self, guardrail):
        """Parenthetical notes with system/technical content must be blocked."""
        narrative = "(Тестер перемещён в новую локацию, HP обновлён до 3)"
        result = guardrail.check_narrative(narrative)
        assert not result.passed, (
            "Parenthetical system note in narrative was NOT caught"
        )
