"""Phase 8: Eval data models — contract compliance.

Tests that dataclasses in contracts/eval_models.py have correct fields,
default values, and types. Spec: docs/specs/observability-evals.md.
"""

from __future__ import annotations

import pytest

from contracts.eval_models import (
    CompanionEvalResult,
    CompanionScores,
    CompressorEvalResult,
    DMEvalResult,
    EvalReport,
    GuardrailEvalResult,
    HolisticEvalResult,
    JudgeScore,
    RAGEvalResult,
    TechnicalMetrics,
)


# ---------------------------------------------------------------------------
# JudgeScore
# ---------------------------------------------------------------------------


class TestJudgeScoreContract:
    """JudgeScore has scores dict, explanation, and optional raw_response."""

    def test_scores_dict_and_explanation(self):
        js = JudgeScore(scores={"facts": 4, "causality": 3}, explanation="ok")
        assert js.scores == {"facts": 4, "causality": 3}
        assert js.explanation == "ok"

    def test_raw_response_defaults_empty(self):
        js = JudgeScore(scores={}, explanation="x")
        assert js.raw_response == ""

    def test_raw_response_can_be_set(self):
        js = JudgeScore(scores={}, explanation="x", raw_response='{"a":1}')
        assert js.raw_response == '{"a":1}'


# ---------------------------------------------------------------------------
# RAGEvalResult
# ---------------------------------------------------------------------------


class TestRAGEvalResultContract:
    """RAGEvalResult fields per contract: hit_rate, total_queries, hits, misses."""

    def test_all_fields_present(self):
        r = RAGEvalResult(hit_rate=0.9, total_queries=10, hits=9)
        assert r.hit_rate == 0.9
        assert r.total_queries == 10
        assert r.hits == 9

    def test_misses_defaults_empty_list(self):
        r = RAGEvalResult(hit_rate=1.0, total_queries=5, hits=5)
        assert r.misses == []

    def test_misses_with_details(self):
        miss = {"query": "test", "expected": ["A"], "got": ["B"]}
        r = RAGEvalResult(hit_rate=0.5, total_queries=2, hits=1, misses=[miss])
        assert len(r.misses) == 1
        assert r.misses[0]["query"] == "test"


# ---------------------------------------------------------------------------
# GuardrailEvalResult
# ---------------------------------------------------------------------------


class TestGuardrailEvalResultContract:
    """GuardrailEvalResult: TP/FP rates, totals, failure lists."""

    def test_all_required_fields(self):
        r = GuardrailEvalResult(
            true_positive_rate=0.95,
            false_positive_rate=0.02,
            total_injections=50,
            total_legitimate=50,
        )
        assert r.true_positive_rate == 0.95
        assert r.false_positive_rate == 0.02

    def test_failure_lists_default_empty(self):
        r = GuardrailEvalResult(
            true_positive_rate=1.0,
            false_positive_rate=0.0,
            total_injections=10,
            total_legitimate=10,
        )
        assert r.false_negatives == []
        assert r.false_positives == []


# ---------------------------------------------------------------------------
# CompressorEvalResult
# ---------------------------------------------------------------------------


class TestCompressorEvalResultContract:
    """CompressorEvalResult has single_compression and multi_compression."""

    def test_single_compression_required(self):
        js = JudgeScore(scores={"facts": 5}, explanation="good")
        r = CompressorEvalResult(single_compression=js)
        assert r.single_compression.scores["facts"] == 5

    def test_multi_compression_defaults_empty(self):
        js = JudgeScore(scores={}, explanation="")
        r = CompressorEvalResult(single_compression=js)
        assert r.multi_compression == []

    def test_multi_compression_list_of_judge_scores(self):
        js = JudgeScore(scores={"facts": 4}, explanation="ok")
        r = CompressorEvalResult(
            single_compression=js,
            multi_compression=[js, js, js],
        )
        assert len(r.multi_compression) == 3


# ---------------------------------------------------------------------------
# DMEvalResult
# ---------------------------------------------------------------------------


class TestDMEvalResultContract:
    """DMEvalResult: rule_compliance, turn count, LLM session-level scores (1-5).

    Contract: contracts/eval_models.py — DMEvalResult.
    """

    def test_required_fields(self):
        r = DMEvalResult(
            rule_compliance=0.95,
            total_turns=20,
        )
        assert r.rule_compliance == 0.95
        assert r.total_turns == 20

    def test_llm_scores_default_zero(self):
        r = DMEvalResult(rule_compliance=1.0, total_turns=5)
        assert r.consistency == 0.0
        assert r.rules_score == 0.0
        assert r.adaptivity == 0.0
        assert r.plot_progression == 0.0
        assert r.repetition == 0.0

    def test_llm_scores_can_be_set(self):
        r = DMEvalResult(
            rule_compliance=0.8,
            total_turns=10,
            consistency=4.0,
            rules_score=3.5,
            adaptivity=4.5,
            plot_progression=3.0,
            repetition=5.0,
        )
        assert r.consistency == 4.0
        assert r.rules_score == 3.5
        assert r.adaptivity == 4.5
        assert r.plot_progression == 3.0
        assert r.repetition == 5.0

    def test_failure_and_highlight_lists_default_empty(self):
        r = DMEvalResult(rule_compliance=1.0, total_turns=5)
        assert r.rule_violations == []
        assert r.llm_issues == []
        assert r.llm_highlights == []


# ---------------------------------------------------------------------------
# CompanionEvalResult
# ---------------------------------------------------------------------------


class TestCompanionEvalResultContract:
    """CompanionEvalResult: list of CompanionScores per companion + total_turns.

    Contract: contracts/eval_models.py — CompanionEvalResult, CompanionScores.
    """

    def test_companions_and_total_turns(self):
        scores = CompanionScores(name="Branka", in_character=4.0, agency=3.5)
        r = CompanionEvalResult(companions=[scores], total_turns=10)
        assert len(r.companions) == 1
        assert r.companions[0].name == "Branka"
        assert r.companions[0].in_character == 4.0
        assert r.total_turns == 10

    def test_companions_defaults_empty(self):
        r = CompanionEvalResult()
        assert r.companions == []
        assert r.total_turns == 0

    def test_companion_scores_defaults_zero(self):
        s = CompanionScores(name="Test")
        assert s.in_character == 0.0
        assert s.agency == 0.0
        assert s.liveliness == 0.0
        assert s.action_variety == 0.0
        assert s.issues == []
        assert s.highlights == []


# ---------------------------------------------------------------------------
# HolisticEvalResult
# ---------------------------------------------------------------------------


class TestHolisticEvalResultContract:
    """HolisticEvalResult: scores, highlights, issues."""

    def test_scores_is_judge_score(self):
        js = JudgeScore(
            scores={"progression": 4, "diversity": 3,
                     "reactivity": 4, "narrative_quality": 5},
            explanation="great session",
        )
        r = HolisticEvalResult(scores=js)
        assert isinstance(r.scores, JudgeScore)
        assert "progression" in r.scores.scores

    def test_highlights_and_issues_default_empty(self):
        js = JudgeScore(scores={}, explanation="")
        r = HolisticEvalResult(scores=js)
        assert r.highlights == []
        assert r.issues == []


# ---------------------------------------------------------------------------
# TechnicalMetrics
# ---------------------------------------------------------------------------


class TestTechnicalMetricsContract:
    """TechnicalMetrics: all numeric fields required."""

    def test_all_fields_present(self):
        m = TechnicalMetrics(
            error_rate=0.01,
            retry_rate=0.05,
            guardrail_block_rate=0.02,
            total_llm_calls=100,
            total_tokens=50000,
            estimated_cost_usd=1.5,
        )
        assert m.error_rate == 0.01
        assert m.retry_rate == 0.05
        assert m.guardrail_block_rate == 0.02
        assert m.total_llm_calls == 100
        assert m.total_tokens == 50000
        assert m.estimated_cost_usd == 1.5


# ---------------------------------------------------------------------------
# EvalReport
# ---------------------------------------------------------------------------


class TestEvalReportContract:
    """EvalReport aggregates all component results, all optional."""

    def test_all_fields_default_none(self):
        r = EvalReport()
        assert r.rag is None
        assert r.guardrails is None
        assert r.compressor is None
        assert r.dm is None
        assert r.companion is None
        assert r.holistic is None
        assert r.technical is None

    def test_model_config_defaults_empty_dict(self):
        r = EvalReport()
        assert r.model_config == {}

    def test_partial_population(self):
        rag = RAGEvalResult(hit_rate=0.9, total_queries=10, hits=9)
        r = EvalReport(rag=rag)
        assert r.rag is not None
        assert r.dm is None
