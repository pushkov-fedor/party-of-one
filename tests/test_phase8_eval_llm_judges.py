"""Phase 8: LLMJudge + CompressorEvaluator behavior tests.

Tests behavior described in contracts/eval.py and docs/specs/observability-evals.md:

- LLMJudge: parse JSON response, handle malformed JSON
- CompressorEvaluator: extract compression events, return JudgeScores

All LLM calls are mocked.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from contracts.eval_models import (
    CompressorEvalResult,
    JudgeScore,
)


# ---------------------------------------------------------------------------
# Helpers: session log entries
# ---------------------------------------------------------------------------


def _dm_turn(turn: int) -> dict[str, Any]:
    return {
        "event": "llm_call",
        "agent": "dm",
        "turn": turn,
        "world_state_snapshot": "hero has 10 HP",
        "dm_response": "The goblin attacks!",
        "commands": [],
    }


def _compression_event(
    cycle: int = 1,
    raw_history: str = "long history...",
    compressed: str = "short summary",
    world_state: str = "hero 10HP",
) -> dict[str, Any]:
    return {
        "event": "compression",
        "cycle": cycle,
        "raw_history": raw_history,
        "compressed_history": compressed,
        "world_state_snapshot": world_state,
    }


# ---------------------------------------------------------------------------
# LLMJudge: happy path
# ---------------------------------------------------------------------------


class TestLLMJudgeHappyPath:
    """LLMJudge parses structured JSON from LLM into JudgeScore.

    Contract: evaluate(prompt) -> JudgeScore.
    """

    def test_returns_judge_score_with_scores_and_explanation(self):
        from party_of_one.eval.llm_judge import LLMJudgeImpl

        llm_response = json.dumps({
            "scores": {"facts": 5, "causality": 4},
            "explanation": "Good compression",
        })
        mock_llm = MagicMock(return_value=llm_response)
        judge = LLMJudgeImpl(llm_call=mock_llm)
        result = judge.evaluate("Rate this compression")

        assert isinstance(result, JudgeScore)
        assert result.scores["facts"] == 5
        assert result.scores["causality"] == 4
        assert "Good" in result.explanation

    def test_raw_response_stored(self):
        from party_of_one.eval.llm_judge import LLMJudgeImpl

        raw = json.dumps({
            "scores": {"x": 3},
            "explanation": "ok",
        })
        mock_llm = MagicMock(return_value=raw)
        judge = LLMJudgeImpl(llm_call=mock_llm)
        result = judge.evaluate("prompt")
        assert result.raw_response == raw


# ---------------------------------------------------------------------------
# LLMJudge: error handling
# ---------------------------------------------------------------------------


class TestLLMJudgeErrorHandling:
    """LLMJudge raises RuntimeError on malformed JSON from LLM.

    Contract: Raises RuntimeError if judge LLM returns unparseable JSON.
    """

    def test_malformed_json_raises_runtime_error(self):
        from party_of_one.eval.llm_judge import LLMJudgeImpl

        mock_llm = MagicMock(return_value="not valid json {{{")
        judge = LLMJudgeImpl(llm_call=mock_llm)

        with pytest.raises(RuntimeError):
            judge.evaluate("Rate this")

    def test_missing_scores_key_raises_runtime_error(self):
        from party_of_one.eval.llm_judge import LLMJudgeImpl

        mock_llm = MagicMock(return_value=json.dumps({"explanation": "no scores"}))
        judge = LLMJudgeImpl(llm_call=mock_llm)

        with pytest.raises(RuntimeError):
            judge.evaluate("Rate this")

    def test_empty_string_raises_runtime_error(self):
        from party_of_one.eval.llm_judge import LLMJudgeImpl

        mock_llm = MagicMock(return_value="")
        judge = LLMJudgeImpl(llm_call=mock_llm)

        with pytest.raises(RuntimeError):
            judge.evaluate("Rate this")


# ---------------------------------------------------------------------------
# CompressorEvaluator: single cycle
# ---------------------------------------------------------------------------


class TestCompressorEvaluatorSingleCycle:
    """CompressorEvaluator extracts compression events, returns JudgeScore.

    Spec: 4 criteria: facts, causality, dm_sufficiency, companion_sufficiency.
    """

    def test_single_compression_returns_judge_score(self):
        from party_of_one.eval.compressor_evaluator import CompressorEvaluatorImpl

        session_log = [_compression_event(cycle=1)]

        mock_judge = MagicMock()
        mock_judge.evaluate.return_value = JudgeScore(
            scores={"facts": 5, "causality": 4,
                     "dm_sufficiency": 5, "companion_sufficiency": 4},
            explanation="ok",
        )
        evaluator = CompressorEvaluatorImpl(judge=mock_judge)
        result = evaluator.evaluate(session_log)

        assert isinstance(result, CompressorEvalResult)
        assert isinstance(result.single_compression, JudgeScore)
        assert "facts" in result.single_compression.scores

    def test_judge_called_with_compression_context(self):
        from party_of_one.eval.compressor_evaluator import CompressorEvaluatorImpl

        session_log = [_compression_event(raw_history="FULL", compressed="SHORT")]

        mock_judge = MagicMock()
        mock_judge.evaluate.return_value = JudgeScore(
            scores={"facts": 3, "causality": 3,
                     "dm_sufficiency": 3, "companion_sufficiency": 3},
            explanation="average",
        )
        evaluator = CompressorEvaluatorImpl(judge=mock_judge)
        evaluator.evaluate(session_log)

        call_args = mock_judge.evaluate.call_args[0][0]
        assert "FULL" in call_args or "SHORT" in call_args


# ---------------------------------------------------------------------------
# CompressorEvaluator: multi-cycle
# ---------------------------------------------------------------------------


class TestCompressorEvaluatorMultiCycle:
    """Spec: multi-compression returns list of JudgeScores, one per cycle."""

    def test_three_cycles_return_multiple_scores(self):
        from party_of_one.eval.compressor_evaluator import CompressorEvaluatorImpl

        session_log = [
            _compression_event(cycle=1),
            _dm_turn(1),
            _compression_event(cycle=2),
            _dm_turn(2),
            _compression_event(cycle=3),
        ]

        mock_judge = MagicMock()
        mock_judge.evaluate.return_value = JudgeScore(
            scores={"facts": 4, "causality": 4,
                     "dm_sufficiency": 4, "companion_sufficiency": 4},
            explanation="ok",
        )
        evaluator = CompressorEvaluatorImpl(judge=mock_judge)
        result = evaluator.evaluate(session_log)

        assert len(result.multi_compression) >= 2

    def test_single_cycle_no_multi_compression(self):
        from party_of_one.eval.compressor_evaluator import CompressorEvaluatorImpl

        session_log = [_compression_event(cycle=1)]

        mock_judge = MagicMock()
        mock_judge.evaluate.return_value = JudgeScore(
            scores={"facts": 5, "causality": 5,
                     "dm_sufficiency": 5, "companion_sufficiency": 5},
            explanation="great",
        )
        evaluator = CompressorEvaluatorImpl(judge=mock_judge)
        result = evaluator.evaluate(session_log)

        assert result.single_compression is not None
        assert isinstance(result.multi_compression, list)
