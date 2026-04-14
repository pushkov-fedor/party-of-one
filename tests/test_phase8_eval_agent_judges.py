"""Phase 8: DMEvaluator, CompanionEvaluator, HolisticEvaluator behavior tests.

Tests behavior described in contracts/eval.py and docs/specs/observability-evals.md.
All LLM calls are mocked.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from contracts.eval_models import (
    CompanionEvalResult, CompanionScores, DMEvalResult,
    HolisticEvalResult, JudgeScore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dm_turn(turn: int, *, dm_response: str = "The goblin attacks!") -> dict[str, Any]:
    return {"event": "llm_call", "agent": "dm", "turn": turn,
            "world_state_snapshot": "hero has 10 HP",
            "dm_response": dm_response, "commands": []}

def _companion_turn(turn: int, *, action: str = "I charge forward!") -> dict[str, Any]:
    return {"event": "llm_call", "agent": "companion", "turn": turn,
            "personality_profile": "brave warrior", "companion_name": "Branka",
            "companion_action": action, "context": "In a dark cave"}

def _tool_use_entry(turn: int = 1) -> dict[str, Any]:
    return {"event": "tool_use", "agent": "dm", "turn": turn,
            "tool": "damage_character", "args": {"id": "g1", "amount": 4}}

def _dm_judge_response(
    *,
    consistency: float = 5,
    rules: float = 5,
    adaptivity: float = 4,
    plot_progression: float = 4,
    repetition: float = 5,
    issues: list[str] | None = None,
    highlights: list[str] | None = None,
) -> str:
    """Build JSON response matching the new DM session-level judge format."""
    return json.dumps({
        "scores": {
            "consistency": consistency,
            "rules": rules,
            "adaptivity": adaptivity,
            "plot_progression": plot_progression,
            "repetition": repetition,
        },
        "issues": issues or [],
        "highlights": highlights or [],
    })


def _companion_judge_response(
    *,
    in_character: float = 5,
    agency: float = 4,
    liveliness: float = 4,
    action_variety: float = 4,
    issues: list[str] | None = None,
    highlights: list[str] | None = None,
) -> str:
    """Build JSON response matching the new companion judge format."""
    return json.dumps({
        "scores": {
            "in_character": in_character,
            "agency": agency,
            "liveliness": liveliness,
            "action_variety": action_variety,
        },
        "issues": issues or [],
        "highlights": highlights or [],
    })


# ---------------------------------------------------------------------------
# DMEvaluator
# ---------------------------------------------------------------------------

class TestDMEvaluatorHappyPath:
    """DMEvaluator does a single session-level LLM call, returns 1-5 scores.

    Contract: evaluate(session_log) -> DMEvalResult with LLM scores.
    """

    def test_good_session_returns_high_scores(self):
        from party_of_one.eval.dm_evaluator import DMEvaluatorImpl
        mock_judge = MagicMock()
        raw = _dm_judge_response(consistency=5, rules=5, adaptivity=4,
                                 plot_progression=4, repetition=5,
                                 highlights=["good pacing"])
        mock_judge.evaluate.return_value = JudgeScore(
            scores={}, explanation="ok", raw_response=raw,
        )
        evaluator = DMEvaluatorImpl(judge=mock_judge)
        result = evaluator.evaluate([_dm_turn(1), _dm_turn(2), _companion_turn(3)])

        assert isinstance(result, DMEvalResult)
        assert result.consistency == pytest.approx(5.0)
        assert result.rules_score == pytest.approx(5.0)
        assert result.adaptivity == pytest.approx(4.0)
        assert result.plot_progression == pytest.approx(4.0)
        assert result.repetition == pytest.approx(5.0)
        assert result.rule_compliance == pytest.approx(1.0)  # rules=5 -> 5/5
        assert result.llm_highlights == ["good pacing"]
        assert result.llm_issues == []

    def test_filters_only_dm_turns(self):
        from party_of_one.eval.dm_evaluator import DMEvaluatorImpl
        mock_judge = MagicMock()
        raw = _dm_judge_response()
        mock_judge.evaluate.return_value = JudgeScore(
            scores={}, explanation="ok", raw_response=raw,
        )
        evaluator = DMEvaluatorImpl(judge=mock_judge)
        result = evaluator.evaluate([
            _dm_turn(1), _companion_turn(2), _tool_use_entry(3), _dm_turn(4),
        ])
        assert result.total_turns == 2


class TestDMEvaluatorLowScores:
    """DMEvaluator populates issues when judge returns low scores."""

    def test_low_consistency_reflected_in_result(self):
        from party_of_one.eval.dm_evaluator import DMEvaluatorImpl
        mock_judge = MagicMock()
        raw = _dm_judge_response(
            consistency=2, rules=3, adaptivity=2,
            plot_progression=2, repetition=1,
            issues=["contradiction with HP", "ignored companion"],
        )
        mock_judge.evaluate.return_value = JudgeScore(
            scores={}, explanation="poor", raw_response=raw,
        )
        evaluator = DMEvaluatorImpl(judge=mock_judge)
        result = evaluator.evaluate([_dm_turn(1), _dm_turn(2)])

        assert result.consistency == pytest.approx(2.0)
        assert result.repetition == pytest.approx(1.0)
        assert len(result.llm_issues) == 2
        assert result.rule_compliance == pytest.approx(3.0 / 5.0)

    def test_low_rules_score_lowers_compliance(self):
        from party_of_one.eval.dm_evaluator import DMEvaluatorImpl
        mock_judge = MagicMock()
        raw = _dm_judge_response(rules=1, issues=["wrong dice"])
        mock_judge.evaluate.return_value = JudgeScore(
            scores={}, explanation="bad", raw_response=raw,
        )
        evaluator = DMEvaluatorImpl(judge=mock_judge)
        result = evaluator.evaluate([_dm_turn(1)])

        assert result.rule_compliance == pytest.approx(1.0 / 5.0)
        assert result.rules_score == pytest.approx(1.0)
        assert "wrong dice" in result.llm_issues


# ---------------------------------------------------------------------------
# CompanionEvaluator
# ---------------------------------------------------------------------------

class TestCompanionEvaluatorHappyPath:
    """CompanionEvaluator batches actions per companion, returns per-companion scores.

    Contract: evaluate(session_log) -> CompanionEvalResult with CompanionScores list.
    """

    def test_good_companion_returns_high_scores(self):
        from party_of_one.eval.companion_evaluator import CompanionEvaluatorImpl
        mock_judge = MagicMock()
        raw = _companion_judge_response(
            in_character=5, agency=4, liveliness=4, action_variety=4,
            highlights=["great roleplay"],
        )
        mock_judge.evaluate.return_value = JudgeScore(
            scores={}, explanation="ok", raw_response=raw,
        )
        evaluator = CompanionEvaluatorImpl(judge=mock_judge)
        result = evaluator.evaluate([
            _companion_turn(1), _companion_turn(2), _dm_turn(3),
        ])

        assert isinstance(result, CompanionEvalResult)
        assert result.total_turns == 2
        assert len(result.companions) == 1
        assert result.companions[0].name == "Branka"
        assert result.companions[0].in_character == pytest.approx(5.0)
        assert result.companions[0].agency == pytest.approx(4.0)
        assert result.companions[0].highlights == ["great roleplay"]
        assert result.companions[0].issues == []

    def test_low_scores_reflected_with_issues(self):
        from party_of_one.eval.companion_evaluator import CompanionEvaluatorImpl
        mock_judge = MagicMock()
        raw = _companion_judge_response(
            in_character=2, agency=1, liveliness=2, action_variety=1,
            issues=["broke character", "passive"],
        )
        mock_judge.evaluate.return_value = JudgeScore(
            scores={}, explanation="poor", raw_response=raw,
        )
        evaluator = CompanionEvaluatorImpl(judge=mock_judge)
        result = evaluator.evaluate([_companion_turn(1), _companion_turn(2)])

        assert result.companions[0].in_character == pytest.approx(2.0)
        assert result.companions[0].agency == pytest.approx(1.0)
        assert len(result.companions[0].issues) == 2

    def test_filters_only_companion_turns(self):
        from party_of_one.eval.companion_evaluator import CompanionEvaluatorImpl
        mock_judge = MagicMock()
        raw = _companion_judge_response()
        mock_judge.evaluate.return_value = JudgeScore(
            scores={}, explanation="ok", raw_response=raw,
        )
        evaluator = CompanionEvaluatorImpl(judge=mock_judge)
        result = evaluator.evaluate([_dm_turn(1), _companion_turn(2), _tool_use_entry(3)])
        assert result.total_turns == 1


# ---------------------------------------------------------------------------
# HolisticEvaluator
# ---------------------------------------------------------------------------

class TestHolisticEvaluator:
    """HolisticEvaluator filters narrative, returns 4-criteria JudgeScore.

    Spec: filters out tool_use and commands; criteria: progression,
    diversity, reactivity, narrative_quality.
    """

    def _make_judge(self, *, highlights=None, issues=None):
        mock_judge = MagicMock()
        mock_judge.evaluate.return_value = JudgeScore(
            scores={"progression": 4, "diversity": 3,
                     "reactivity": 4, "narrative_quality": 5},
            explanation="great",
            raw_response=json.dumps({
                "scores": {"progression": 4, "diversity": 3,
                           "reactivity": 4, "narrative_quality": 5},
                "highlights": highlights or [],
                "issues": issues or [],
            }),
        )
        return mock_judge

    def test_returns_holistic_result_with_4_criteria(self):
        from party_of_one.eval.holistic_evaluator import HolisticEvaluatorImpl
        judge = self._make_judge(highlights=["epic battle"], issues=["pacing slow"])
        evaluator = HolisticEvaluatorImpl(judge=judge)
        result = evaluator.evaluate([_dm_turn(1), _companion_turn(2), _tool_use_entry(3)])

        assert isinstance(result, HolisticEvalResult)
        for key in ("progression", "diversity", "reactivity", "narrative_quality"):
            assert key in result.scores.scores

    def test_filters_tool_use_from_narrative(self):
        from party_of_one.eval.holistic_evaluator import HolisticEvaluatorImpl
        judge = self._make_judge()
        evaluator = HolisticEvaluatorImpl(judge=judge)
        evaluator.evaluate([_dm_turn(1), _tool_use_entry(2), _companion_turn(3)])

        prompt = judge.evaluate.call_args[0][0]
        assert "damage_character" not in prompt

    def test_highlights_and_issues_populated(self):
        from party_of_one.eval.holistic_evaluator import HolisticEvaluatorImpl
        judge = self._make_judge(highlights=["brave sacrifice"], issues=["repetitive"])
        evaluator = HolisticEvaluatorImpl(judge=judge)
        result = evaluator.evaluate([_dm_turn(1), _companion_turn(2)])

        assert isinstance(result.highlights, list)
        assert isinstance(result.issues, list)
