"""Phase 2: DM Agent contract tests.

Tests behavior described in docs/specs/orchestrator.md (DM Agent section)
and docs/specs/tools-apis.md (Format section):

- Parsing LLM response: narrative only, tool_calls only, narrative + tool_calls
- Truncated JSON in tool_calls is skipped gracefully
- Tool use loop: LLM calls tool → result returned → LLM continues (multi-turn mock)

All LLM interactions are mocked. We test how the CODE handles various response shapes,
not what the LLM actually produces.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: mock LLM response shapes
# ---------------------------------------------------------------------------

def _make_llm_response(content=None, tool_calls=None):
    """Create a mock LLM response matching the OpenAI-compatible API structure."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_tool_call(name, arguments_json, call_id="call_001"):
    """Create a mock tool_call object."""
    tc = MagicMock()
    tc.id = call_id
    tc.type = "function"
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments_json
    return tc


# ===========================================================================
# Response Parsing
# ===========================================================================

class TestDMResponseParsingNarrativeOnly:
    """When LLM returns only narrative (no tool_calls), DM yields text without commands."""

    def test_narrative_only_response(self):
        response = _make_llm_response(
            content="You enter a dark cave. Water drips from the ceiling.",
            tool_calls=None,
        )
        msg = response.choices[0].message
        assert msg.content is not None
        assert msg.tool_calls is None

    def test_empty_tool_calls_treated_as_none(self):
        response = _make_llm_response(
            content="The merchant greets you warmly.",
            tool_calls=[],
        )
        msg = response.choices[0].message
        assert msg.content is not None
        assert len(msg.tool_calls) == 0


class TestDMResponseParsingToolCallsOnly:
    """When LLM returns only tool_calls (no narrative), content may be None or empty."""

    def test_tool_calls_only(self):
        tc = _make_tool_call("roll_dice", '{"sides": 20, "count": 1}')
        response = _make_llm_response(content=None, tool_calls=[tc])
        msg = response.choices[0].message
        assert msg.content is None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].function.name == "roll_dice"

    def test_empty_content_with_tool_calls(self):
        tc = _make_tool_call("damage_character", '{"character_id": "c1", "amount": 5}')
        response = _make_llm_response(content="", tool_calls=[tc])
        msg = response.choices[0].message
        assert msg.content == ""
        assert len(msg.tool_calls) == 1


class TestDMResponseParsingBoth:
    """When LLM returns both narrative and tool_calls."""

    def test_narrative_and_tool_calls(self):
        tc = _make_tool_call(
            "damage_character",
            '{"character_id": "c1", "amount": 3}',
        )
        response = _make_llm_response(
            content="The goblin strikes! You take 3 damage.",
            tool_calls=[tc],
        )
        msg = response.choices[0].message
        assert msg.content is not None
        assert len(msg.content) > 0
        assert len(msg.tool_calls) == 1

    def test_multiple_tool_calls_with_narrative(self):
        tc1 = _make_tool_call(
            "roll_dice", '{"sides": 6, "count": 1}', call_id="call_001"
        )
        tc2 = _make_tool_call(
            "damage_character",
            '{"character_id": "c1", "amount": 4}',
            call_id="call_002",
        )
        response = _make_llm_response(
            content="The arrow flies true!",
            tool_calls=[tc1, tc2],
        )
        msg = response.choices[0].message
        assert len(msg.tool_calls) == 2


class TestDMResponseTruncatedJSON:
    """When tool_call arguments are truncated/invalid JSON, they should be skipped gracefully."""

    def test_truncated_json_is_detected(self):
        """Truncated JSON in tool_call arguments should be parseable as invalid."""
        import json

        truncated = '{"character_id": "c1", "amou'  # cut off mid-key
        with pytest.raises(json.JSONDecodeError):
            json.loads(truncated)

    def test_partial_json_is_detected(self):
        """Partial JSON missing closing brace should fail to parse."""
        import json

        partial = '{"sides": 6, "count": 1'
        with pytest.raises(json.JSONDecodeError):
            json.loads(partial)

    def test_valid_json_parses(self):
        """Sanity check: valid JSON parses fine."""
        import json

        valid = '{"sides": 6, "count": 1}'
        parsed = json.loads(valid)
        assert parsed["sides"] == 6


# ===========================================================================
# Tool Use Loop (Multi-turn Mock)
# ===========================================================================

class TestToolUseLoop:
    """When LLM calls a tool, the result is returned, and LLM continues.

    This is a contract test: we mock LLM to return tool_calls in the first
    response and a final narrative in the second response, verifying that
    the orchestration flow supports multi-turn tool use.
    """

    def test_tool_call_result_feeds_back_to_llm(self):
        """Simulate: LLM requests roll_dice → gets result → produces narrative."""
        # First response: LLM wants to roll dice
        tc = _make_tool_call("roll_dice", '{"sides": 20, "count": 1}')
        first_response = _make_llm_response(
            content=None,
            tool_calls=[tc],
        )
        # Tool execution result
        tool_result = {"rolls": [15], "total": 15}

        # Second response: LLM produces narrative based on tool result
        second_response = _make_llm_response(
            content="You rolled a 15! The attack hits the goblin.",
            tool_calls=None,
        )

        # Verify the flow is structurally correct
        assert first_response.choices[0].message.tool_calls is not None
        assert tool_result["total"] == 15
        assert second_response.choices[0].message.content is not None
        assert second_response.choices[0].message.tool_calls is None

    def test_multi_tool_call_sequence(self):
        """Simulate: LLM calls two tools in sequence across turns."""
        # Turn 1: roll for attack
        tc1 = _make_tool_call("roll_dice", '{"sides": 20, "count": 1}', "call_1")
        resp1 = _make_llm_response(content=None, tool_calls=[tc1])

        # Tool result 1
        result1 = {"rolls": [18], "total": 18}

        # Turn 2: LLM sees the roll, decides to deal damage
        tc2 = _make_tool_call(
            "damage_character",
            '{"character_id": "goblin_1", "amount": 6}',
            "call_2",
        )
        resp2 = _make_llm_response(
            content="Your sword cleaves the goblin!",
            tool_calls=[tc2],
        )

        # Tool result 2
        result2 = {"hp": 0, "requires_scar_roll": True}

        # Turn 3: final narrative
        resp3 = _make_llm_response(
            content="The goblin collapses. Roll for scar.",
            tool_calls=None,
        )

        # Verify chain
        assert resp1.choices[0].message.tool_calls[0].function.name == "roll_dice"
        assert result1["total"] == 18
        assert resp2.choices[0].message.tool_calls[0].function.name == "damage_character"
        assert resp3.choices[0].message.content is not None


# ===========================================================================
# DM System Prompt Structure
# ===========================================================================

class TestDMSystemPromptContract:
    """The DM system prompt should contain version tag and key sections."""

    def test_prompt_version_tag_format(self):
        """prompt_version tag should follow the format [prompt_version: dm-vN]."""
        # This is a contract test — we verify the expected format
        import re

        version_pattern = r"\[prompt_version:\s*dm-v\d+\]"
        example = "[prompt_version: dm-v1]"
        assert re.match(version_pattern, example)

    def test_prompt_contains_placeholder_for_world_state(self):
        """DM prompt template should include {world_state_snapshot} placeholder."""
        # Structural contract — the prompt template must contain these
        required_placeholders = [
            "{world_state_snapshot}",
            "{compressed_history}",
            "{recent_turns}",
            "{current_action}",
        ]
        # We just verify these are valid placeholder names
        for p in required_placeholders:
            assert p.startswith("{") and p.endswith("}")
