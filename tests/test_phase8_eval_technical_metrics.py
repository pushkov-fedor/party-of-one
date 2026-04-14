"""Phase 8: TechnicalMetrics + property invariants.

Tests behavior described in contracts/eval_models.py and
docs/specs/observability-evals.md:

- TechnicalMetrics: computed from log entries without LLM
- Property invariants: rates between 0-1, tokens non-negative, etc.
"""

from __future__ import annotations

from typing import Any

import pytest

from contracts.eval_models import (
    CompanionEvalResult,
    DMEvalResult,
    GuardrailEvalResult,
    RAGEvalResult,
    TechnicalMetrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_call(
    *,
    error: str | None = None,
    retries: int = 0,
    guardrail_pre: str = "pass",
    prompt_tokens: int = 1000,
    completion_tokens: int = 500,
    model: str = "openai/gpt-4.1",
) -> dict[str, Any]:
    return {
        "event": "llm_call",
        "agent": "dm",
        "error": error,
        "retries": retries,
        "guardrail_pre": guardrail_pre,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "model": model,
    }


# ---------------------------------------------------------------------------
# TechnicalMetrics: computation
# ---------------------------------------------------------------------------


class TestTechnicalMetricsComputation:
    """TechnicalMetrics computed from log entries without LLM.

    Spec: error_rate = errored / total, retry_rate = retried / total,
    guardrail_block_rate = blocked / total. Tokens summed, cost estimated.
    """

    def test_all_clean_calls(self):
        from party_of_one.eval.technical_metrics import compute_technical_metrics

        log = [_llm_call(), _llm_call(), _llm_call()]
        m = compute_technical_metrics(log)

        assert isinstance(m, TechnicalMetrics)
        assert m.error_rate == pytest.approx(0.0)
        assert m.retry_rate == pytest.approx(0.0)
        assert m.guardrail_block_rate == pytest.approx(0.0)
        assert m.total_llm_calls == 3

    def test_error_rate_counted(self):
        from party_of_one.eval.technical_metrics import compute_technical_metrics

        log = [_llm_call(), _llm_call(error="timeout"), _llm_call()]
        m = compute_technical_metrics(log)
        assert m.error_rate == pytest.approx(1 / 3)

    def test_retry_rate_counted(self):
        from party_of_one.eval.technical_metrics import compute_technical_metrics

        log = [_llm_call(retries=0), _llm_call(retries=2)]
        m = compute_technical_metrics(log)
        assert m.retry_rate == pytest.approx(0.5)

    def test_guardrail_block_rate_counted(self):
        from party_of_one.eval.technical_metrics import compute_technical_metrics

        log = [
            _llm_call(guardrail_pre="pass"),
            _llm_call(guardrail_pre="blocked"),
            _llm_call(guardrail_pre="pass"),
            _llm_call(guardrail_pre="blocked"),
        ]
        m = compute_technical_metrics(log)
        assert m.guardrail_block_rate == pytest.approx(0.5)

    def test_tokens_summed(self):
        from party_of_one.eval.technical_metrics import compute_technical_metrics

        log = [
            _llm_call(prompt_tokens=100, completion_tokens=50),
            _llm_call(prompt_tokens=200, completion_tokens=100),
        ]
        m = compute_technical_metrics(log)
        assert m.total_tokens == 450

    def test_cost_estimated_positive(self):
        from party_of_one.eval.technical_metrics import compute_technical_metrics

        log = [_llm_call(prompt_tokens=5000, completion_tokens=2000)]
        m = compute_technical_metrics(log)
        assert m.estimated_cost_usd > 0


# ---------------------------------------------------------------------------
# TechnicalMetrics: edge cases
# ---------------------------------------------------------------------------


class TestTechnicalMetricsEdgeCases:
    """Edge cases for TechnicalMetrics computation."""

    def test_empty_log(self):
        from party_of_one.eval.technical_metrics import compute_technical_metrics

        m = compute_technical_metrics([])
        assert isinstance(m, TechnicalMetrics)
        assert m.total_llm_calls == 0
        assert m.total_tokens == 0

    def test_non_llm_events_ignored(self):
        from party_of_one.eval.technical_metrics import compute_technical_metrics

        log = [
            _llm_call(),
            {"event": "compression", "cycle": 1},
            {"event": "session_start"},
            _llm_call(),
        ]
        m = compute_technical_metrics(log)
        assert m.total_llm_calls == 2

    def test_all_errors(self):
        from party_of_one.eval.technical_metrics import compute_technical_metrics

        log = [_llm_call(error="e1"), _llm_call(error="e2")]
        m = compute_technical_metrics(log)
        assert m.error_rate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Property invariants
# ---------------------------------------------------------------------------


class TestEvalInvariants:
    """Properties that must always hold for eval result dataclasses."""

    def test_rag_hits_plus_misses_equals_total(self):
        r = RAGEvalResult(
            hit_rate=0.6, total_queries=10, hits=6,
            misses=[{"q": "m"}] * 4,
        )
        assert r.hits + len(r.misses) == r.total_queries

    @pytest.mark.parametrize("rate", [0.0, 0.5, 1.0])
    def test_rag_hit_rate_between_0_and_1(self, rate):
        r = RAGEvalResult(
            hit_rate=rate, total_queries=10, hits=int(rate * 10),
        )
        assert 0.0 <= r.hit_rate <= 1.0

    def test_guardrail_rates_between_0_and_1(self):
        r = GuardrailEvalResult(
            true_positive_rate=0.9, false_positive_rate=0.05,
            total_injections=50, total_legitimate=50,
        )
        assert 0.0 <= r.true_positive_rate <= 1.0
        assert 0.0 <= r.false_positive_rate <= 1.0

    def test_dm_rates_between_0_and_1(self):
        r = DMEvalResult(
            rule_compliance=0.95, total_turns=10,
            consistency=4.0, rules_score=4.5, adaptivity=4.0,
            plot_progression=3.5, repetition=5.0,
        )
        assert 0.0 <= r.rule_compliance <= 1.0
        for score in (r.consistency, r.rules_score, r.adaptivity,
                      r.plot_progression, r.repetition):
            assert 0.0 <= score <= 5.0

    def test_companion_scores_between_0_and_5(self):
        from contracts.eval_models import CompanionScores
        s = CompanionScores(
            name="Branka", in_character=4.5, agency=3.0,
            liveliness=4.0, action_variety=3.5,
        )
        r = CompanionEvalResult(companions=[s], total_turns=10)
        for companion in r.companions:
            for score in (companion.in_character, companion.agency,
                          companion.liveliness, companion.action_variety):
                assert 0.0 <= score <= 5.0

    def test_technical_metrics_non_negative(self):
        m = TechnicalMetrics(
            error_rate=0.0, retry_rate=0.0, guardrail_block_rate=0.0,
            total_llm_calls=0, total_tokens=0, estimated_cost_usd=0.0,
        )
        assert m.error_rate >= 0
        assert m.retry_rate >= 0
        assert m.total_tokens >= 0
        assert m.estimated_cost_usd >= 0
