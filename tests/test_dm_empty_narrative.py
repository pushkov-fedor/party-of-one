"""DM Agent: empty narrative bug regression test.

Bug: _tool_use_loop exits immediately when LLM returns empty content
with no tool_calls, instead of retrying. This causes the DM to "go silent"
-- companion acts but the world doesn't respond.

Contract ref: contracts/dm_agent.py — DMAgent.generate() must return
DMResponse with meaningful narrative. Empty narrative without tool_calls
means the LLM failed to produce output and the agent should retry.

Spec ref: docs/specs/orchestrator.md — DM Agent is the primary narrative
agent; silence (empty narrative) is never a valid final response.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from party_of_one.config import LLMConfig
from party_of_one.models import (
    Character,
    CharacterRole,
    CompanionPersonality,
    CompanionProfile,
    DMResponse,
    Disposition,
    Turn,
    TurnRole,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_response(content=None, tool_calls=None):
    """Build a mock OpenAI-compatible ChatCompletion response."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    # model_dump needed for tool_use_loop message re-injection
    message.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": None,
    }
    choice = MagicMock()
    choice.message = message
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 0 if content is None else 50
    response.usage = usage
    return response


def _make_dm_agent(call_with_retry_mock):
    """Create a DMAgent with mocked LLM client and no tool executor."""
    from party_of_one.agents.dm import DMAgent

    config = LLMConfig(
        model="test-model",
        max_retries=3,
        timeout_seconds=10,
    )
    with patch(
        "party_of_one.agents.dm.create_openrouter_client",
        return_value=MagicMock(),
    ):
        agent = DMAgent(config=config, tool_executor=None)
    return agent


# ===========================================================================
# Empty narrative: _tool_use_loop should retry, not return silence
# ===========================================================================

class TestDMEmptyNarrativeRetry:
    """When LLM returns empty content without tool_calls, the DM agent
    should retry rather than returning an empty narrative.

    Bug: _tool_use_loop exits on the first response with no tool_calls,
    even if narrative is empty. Expected: retry with a nudge message.
    """

    @patch("party_of_one.agents.dm.call_with_retry")
    def test_empty_narrative_no_tools_triggers_retry(self, mock_call):
        """If LLM returns empty content and no tool_calls, the agent
        must not return empty narrative -- it should retry and eventually
        return a non-empty narrative."""
        # First call: LLM returns empty content, no tool_calls
        empty_response = _make_openai_response(content="", tool_calls=None)
        # Second call: LLM returns proper narrative
        good_response = _make_openai_response(
            content="You step into the dark cave. Water drips from the ceiling.",
            tool_calls=None,
        )
        mock_call.side_effect = [empty_response, good_response]

        agent = _make_dm_agent(mock_call)
        result = agent._tool_use_loop(
            [{"role": "user", "content": "Test prompt"}]
        )

        assert isinstance(result, DMResponse)
        assert len(result.narrative.strip()) > 0, (
            "DM returned empty narrative -- the agent should have retried "
            "when LLM produced empty content without tool_calls"
        )

    @patch("party_of_one.agents.dm.call_with_retry")
    def test_none_content_no_tools_triggers_retry(self, mock_call):
        """If LLM returns None content and no tool_calls, the agent
        must not return empty narrative -- it should retry."""
        # First call: LLM returns None content, no tool_calls
        empty_response = _make_openai_response(content=None, tool_calls=None)
        # Second call: LLM returns proper narrative
        good_response = _make_openai_response(
            content="The merchant eyes you suspiciously.",
            tool_calls=None,
        )
        mock_call.side_effect = [empty_response, good_response]

        agent = _make_dm_agent(mock_call)
        result = agent._tool_use_loop(
            [{"role": "user", "content": "Test prompt"}]
        )

        assert isinstance(result, DMResponse)
        assert len(result.narrative.strip()) > 0, (
            "DM returned empty narrative from None content -- "
            "the agent should have retried"
        )

    @patch("party_of_one.agents.dm.call_with_retry")
    def test_whitespace_only_content_triggers_retry(self, mock_call):
        """If LLM returns whitespace-only content and no tool_calls,
        treat it as empty and retry."""
        empty_response = _make_openai_response(
            content="   \n  ", tool_calls=None,
        )
        good_response = _make_openai_response(
            content="A goblin leaps from the shadows!",
            tool_calls=None,
        )
        mock_call.side_effect = [empty_response, good_response]

        agent = _make_dm_agent(mock_call)
        result = agent._tool_use_loop(
            [{"role": "user", "content": "Test prompt"}]
        )

        assert isinstance(result, DMResponse)
        assert len(result.narrative.strip()) > 0, (
            "DM returned whitespace-only narrative -- "
            "the agent should have retried"
        )


class TestDMEmptyNarrativeViaGenerate:
    """Same empty-narrative bug, tested through the public generate() method.

    This verifies the bug surfaces through the contract-level API,
    not just the internal _tool_use_loop.
    """

    @patch("party_of_one.agents.dm.call_with_retry")
    @patch("party_of_one.agents.dm.get_prompt", return_value="Test prompt {world_state_snapshot} {rag_section} {history_section} {current_action}")
    def test_generate_does_not_return_empty_narrative(
        self, mock_prompt, mock_call,
    ):
        """DMAgent.generate() must not return empty narrative when the
        LLM produces empty content without tool_calls."""
        empty_response = _make_openai_response(content="", tool_calls=None)
        good_response = _make_openai_response(
            content="The sword gleams in the torchlight.",
            tool_calls=None,
        )
        mock_call.side_effect = [empty_response, good_response]

        agent = _make_dm_agent(mock_call)
        result = agent.generate(
            action="I look around",
            actor_role=TurnRole.PLAYER,
            world_state_snapshot="Hero has 10 HP",
            compressed_history="",
            recent_turns=[],
            rag_results="",
        )

        assert isinstance(result, DMResponse)
        assert len(result.narrative.strip()) > 0, (
            "generate() returned empty narrative -- "
            "the agent should retry when LLM returns empty content"
        )


class TestDMEmptyNarrativeMultipleRetries:
    """When LLM returns empty content repeatedly, the agent should keep
    retrying within max_rounds limit."""

    @patch("party_of_one.agents.dm.call_with_retry")
    def test_multiple_empty_responses_eventually_succeeds(self, mock_call):
        """If LLM returns empty content 3 times then a real narrative,
        the final result must have the real narrative."""
        empties = [
            _make_openai_response(content="", tool_calls=None)
            for _ in range(3)
        ]
        good = _make_openai_response(
            content="You hear a distant roar echoing through the cavern.",
            tool_calls=None,
        )
        mock_call.side_effect = empties + [good]

        agent = _make_dm_agent(mock_call)
        result = agent._tool_use_loop(
            [{"role": "user", "content": "Test prompt"}],
            max_rounds=20,
        )

        assert isinstance(result, DMResponse)
        assert len(result.narrative.strip()) > 0, (
            "After 3 empty responses, the 4th had real narrative -- "
            "but the agent stopped at the first empty response"
        )

    @patch("party_of_one.agents.dm.call_with_retry")
    def test_all_empty_returns_fallback_not_silence(self, mock_call):
        """If LLM returns empty content for ALL max_rounds iterations,
        the agent should return some fallback rather than empty string."""
        max_rounds = 5
        empties = [
            _make_openai_response(content="", tool_calls=None)
            for _ in range(max_rounds)
        ]
        mock_call.side_effect = empties

        agent = _make_dm_agent(mock_call)
        result = agent._tool_use_loop(
            [{"role": "user", "content": "Test prompt"}],
            max_rounds=max_rounds,
        )

        # Even if all retries fail, the result should not be completely empty.
        # The agent should provide at minimum a fallback message.
        assert isinstance(result, DMResponse)
        assert len(result.narrative.strip()) > 0, (
            "All LLM responses were empty -- the agent should return "
            "a fallback narrative rather than silence"
        )


class TestDMNonEmptyNarrativeReturnsImmediately:
    """Sanity check: when LLM returns a proper narrative, the loop should
    NOT retry -- it should return the narrative immediately.

    This ensures the fix for empty narratives doesn't break the happy path.
    """

    @patch("party_of_one.agents.dm.call_with_retry")
    def test_good_narrative_returned_without_retry(self, mock_call):
        """A non-empty narrative with no tool_calls should be returned
        on the first iteration without retry."""
        good_response = _make_openai_response(
            content="The village square bustles with activity.",
            tool_calls=None,
        )
        mock_call.side_effect = [good_response]

        agent = _make_dm_agent(mock_call)
        result = agent._tool_use_loop(
            [{"role": "user", "content": "Test prompt"}]
        )

        assert result.narrative == "The village square bustles with activity."
        assert mock_call.call_count == 1, (
            "Good narrative should be returned on the first call, no retry"
        )
