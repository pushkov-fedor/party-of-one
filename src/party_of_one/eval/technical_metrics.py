"""Compute technical metrics from session log entries.

No LLM calls — pure aggregation over JSONL log records.
"""

from __future__ import annotations

from typing import Any

from contracts.eval_models import TechnicalMetrics

# Rough per-token cost estimates (USD) for common models.
_COST_PER_TOKEN: dict[str, float] = {
    "openai/gpt-4.1": 2e-6,
    "openai/gpt-4.1-mini": 0.4e-6,
}
_DEFAULT_COST_PER_TOKEN = 1e-6


def compute_technical_metrics(
    log: list[dict[str, Any]],
) -> TechnicalMetrics:
    """Aggregate technical metrics from session log.

    Only considers entries with ``event == "llm_call"``.
    """
    llm_entries = [e for e in log if e.get("event") == "llm_call"]

    total = len(llm_entries)
    if total == 0:
        return TechnicalMetrics(
            error_rate=0.0,
            retry_rate=0.0,
            guardrail_block_rate=0.0,
            total_llm_calls=0,
            total_tokens=0,
            estimated_cost_usd=0.0,
        )

    errors = sum(1 for e in llm_entries if e.get("error"))
    retried = sum(1 for e in llm_entries if e.get("retries", 0) > 0)
    blocked = sum(
        1 for e in llm_entries if e.get("guardrail_pre") == "blocked"
    )

    total_tokens = sum(
        e.get("prompt_tokens", 0) + e.get("completion_tokens", 0)
        for e in llm_entries
    )

    cost = 0.0
    for e in llm_entries:
        model = e.get("model", "")
        cpt = _COST_PER_TOKEN.get(model, _DEFAULT_COST_PER_TOKEN)
        tokens = e.get("prompt_tokens", 0) + e.get("completion_tokens", 0)
        cost += tokens * cpt

    return TechnicalMetrics(
        error_rate=errors / total,
        retry_rate=retried / total,
        guardrail_block_rate=blocked / total,
        total_llm_calls=total,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
    )
