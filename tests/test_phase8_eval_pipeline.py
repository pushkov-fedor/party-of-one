"""Phase 8: EvalPipeline behavior tests.

Tests behavior described in contracts/eval.py and docs/specs/observability-evals.md:

- EvalPipeline.run_component: runs single eval, populates only that field
- EvalPipeline.run_full: populates all fields, stores model_config

All component evaluators and LLM calls are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

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
)


# ---------------------------------------------------------------------------
# EvalPipeline: run_component
# ---------------------------------------------------------------------------


class TestEvalPipelineRunComponent:
    """EvalPipeline.run_component runs single eval, populates one field.

    Contract: run_component(component) -> EvalReport with only that field set.
    """

    def test_run_rag_populates_only_rag(self):
        from party_of_one.eval.pipeline import EvalPipelineImpl

        mock_rag_eval = MagicMock()
        mock_rag_eval.evaluate.return_value = RAGEvalResult(
            hit_rate=0.9, total_queries=10, hits=9,
        )
        pipeline = EvalPipelineImpl(rag_evaluator=mock_rag_eval)
        report = pipeline.run_component("rag")

        assert isinstance(report, EvalReport)
        assert report.rag is not None
        assert report.rag.hit_rate == pytest.approx(0.9)
        assert report.guardrails is None
        assert report.dm is None
        assert report.companion is None
        assert report.holistic is None

    def test_run_guardrails_populates_only_guardrails(self):
        from party_of_one.eval.pipeline import EvalPipelineImpl

        mock_guard_eval = MagicMock()
        mock_guard_eval.evaluate.return_value = GuardrailEvalResult(
            true_positive_rate=0.95,
            false_positive_rate=0.03,
            total_injections=50,
            total_legitimate=50,
        )
        pipeline = EvalPipelineImpl(guardrail_evaluator=mock_guard_eval)
        report = pipeline.run_component("guardrails")

        assert isinstance(report, EvalReport)
        assert report.guardrails is not None
        assert report.guardrails.true_positive_rate == pytest.approx(0.95)
        assert report.rag is None

    @pytest.mark.parametrize("component", [
        "rag", "guardrails", "compressor", "dm", "companion", "holistic",
    ])
    def test_run_component_returns_eval_report(self, component):
        from party_of_one.eval.pipeline import EvalPipelineImpl

        js = JudgeScore(scores={}, explanation="")
        mock_evaluators = {
            "rag_evaluator": MagicMock(),
            "guardrail_evaluator": MagicMock(),
            "compressor_evaluator": MagicMock(),
            "dm_evaluator": MagicMock(),
            "companion_evaluator": MagicMock(),
            "holistic_evaluator": MagicMock(),
        }
        mock_evaluators["rag_evaluator"].evaluate.return_value = RAGEvalResult(
            hit_rate=0.9, total_queries=1, hits=1,
        )
        mock_evaluators["guardrail_evaluator"].evaluate.return_value = (
            GuardrailEvalResult(
                true_positive_rate=0.9, false_positive_rate=0.1,
                total_injections=1, total_legitimate=1,
            )
        )
        mock_evaluators["compressor_evaluator"].evaluate.return_value = (
            CompressorEvalResult(single_compression=js)
        )
        mock_evaluators["dm_evaluator"].evaluate.return_value = DMEvalResult(
            rule_compliance=0.9, total_turns=1, consistency=4.0,
            rules_score=4.5, adaptivity=4.0, plot_progression=3.5,
            repetition=4.0,
        )
        mock_evaluators["companion_evaluator"].evaluate.return_value = (
            CompanionEvalResult(
                companions=[CompanionScores(name="Branka", in_character=4.5)],
                total_turns=1,
            )
        )
        mock_evaluators["holistic_evaluator"].evaluate.return_value = (
            HolisticEvalResult(scores=js)
        )

        pipeline = EvalPipelineImpl(**mock_evaluators)
        report = pipeline.run_component(component)
        assert isinstance(report, EvalReport)


# ---------------------------------------------------------------------------
# EvalPipeline: run_full
# ---------------------------------------------------------------------------


class TestEvalPipelineRunFull:
    """EvalPipeline.run_full populates all fields in EvalReport.

    Contract: run_full() -> complete EvalReport.
    Spec: runs watch mode, then all component evals + technical metrics.
    """

    @pytest.fixture
    def full_pipeline(self):
        from party_of_one.eval.pipeline import EvalPipelineImpl

        js = JudgeScore(scores={"x": 4}, explanation="ok")
        mocks = {
            "rag_evaluator": MagicMock(),
            "guardrail_evaluator": MagicMock(),
            "compressor_evaluator": MagicMock(),
            "dm_evaluator": MagicMock(),
            "companion_evaluator": MagicMock(),
            "holistic_evaluator": MagicMock(),
            "watch_mode_runner": MagicMock(),
        }
        mocks["rag_evaluator"].evaluate.return_value = RAGEvalResult(
            hit_rate=0.9, total_queries=10, hits=9,
        )
        mocks["guardrail_evaluator"].evaluate.return_value = GuardrailEvalResult(
            true_positive_rate=0.9, false_positive_rate=0.05,
            total_injections=50, total_legitimate=50,
        )
        mocks["compressor_evaluator"].evaluate.return_value = (
            CompressorEvalResult(single_compression=js)
        )
        mocks["dm_evaluator"].evaluate.return_value = DMEvalResult(
            rule_compliance=0.95, total_turns=10, consistency=4.5,
            rules_score=4.5, adaptivity=4.0, plot_progression=4.0,
            repetition=5.0,
        )
        mocks["companion_evaluator"].evaluate.return_value = CompanionEvalResult(
            companions=[CompanionScores(name="Branka", in_character=4.5)],
            total_turns=10,
        )
        mocks["holistic_evaluator"].evaluate.return_value = HolisticEvalResult(
            scores=js,
        )
        mocks["watch_mode_runner"].return_value = [
            {"event": "llm_call", "agent": "dm", "error": None,
             "retries": 0, "guardrail_pre": "pass",
             "prompt_tokens": 1000, "completion_tokens": 500, "model": "m"},
        ]
        return EvalPipelineImpl(**mocks)

    def test_run_full_populates_all_fields(self, full_pipeline):
        report = full_pipeline.run_full(rounds=5)

        assert isinstance(report, EvalReport)
        assert report.rag is not None
        assert report.guardrails is not None
        assert report.compressor is not None
        assert report.dm is not None
        assert report.companion is not None
        assert report.holistic is not None
        assert report.technical is not None

    def test_run_full_with_model_overrides_stores_config(self, full_pipeline):
        report = full_pipeline.run_full(
            rounds=5,
            dm_model="openai/gpt-4.1",
            companion_model="openai/gpt-4.1-mini",
        )

        assert report.model_config.get("dm_model") == "openai/gpt-4.1"
        assert report.model_config.get("companion_model") == "openai/gpt-4.1-mini"

    def test_run_full_without_model_overrides_config_empty_or_default(
        self, full_pipeline,
    ):
        report = full_pipeline.run_full(rounds=3)
        assert isinstance(report.model_config, dict)
