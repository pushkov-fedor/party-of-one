"""RAG retriever quality evaluator — deterministic, no LLM."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contracts.eval import RAGEvaluator
from contracts.eval_models import RAGEvalResult
from contracts.retriever import Retriever

from party_of_one.eval.utils import load_jsonl


class RAGEvaluatorImpl(RAGEvaluator):
    """Runs golden queries through the retriever and computes metrics.

    Supports two matching modes:
    - subsection-based: checks if chunk subsection matches expected
    - content-based: checks if chunk text contains expected_context snippet

    If entry has 'expected_context', uses content-based (preferred).
    Falls back to 'expected_subsections' for backwards compat.
    """

    def __init__(self, *, retriever: Retriever) -> None:
        self._retriever = retriever

    def evaluate(self, dataset_path: str | Path) -> RAGEvalResult:
        entries = load_jsonl(dataset_path)

        hits = 0
        context_hits = 0
        misses: list[dict[str, Any]] = []
        reciprocal_ranks: list[float] = []
        precisions: list[float] = []

        for entry in entries:
            query = entry["query"]
            result = self._retriever.search(query)
            chunk_texts = [c.text for c in result.chunks]
            chunk_subs = [c.subsection for c in result.chunks]

            # Content-based matching (preferred)
            expected_ctx = entry.get("expected_context", [])
            if expected_ctx:
                is_hit, rr, prec = self._match_content(
                    chunk_texts, expected_ctx,
                )
                if is_hit:
                    context_hits += 1
            else:
                is_hit, rr, prec = False, 0.0, 0.0

            # Subsection-based matching (fallback or additional)
            expected_subs = set(entry.get("expected_subsections", []))
            if expected_subs:
                found_subs = set(chunk_subs)
                sub_hit = bool(found_subs & expected_subs)
                if not expected_ctx:
                    is_hit = sub_hit
                    rr = self._calc_rr(chunk_subs, expected_subs)
                    prec = self._calc_precision(chunk_subs, expected_subs)

            if is_hit:
                hits += 1
            else:
                misses.append({
                    "query": query,
                    "expected_context": expected_ctx or list(expected_subs),
                    "got_subsections": chunk_subs,
                    "got_preview": [t[:100] for t in chunk_texts],
                })

            reciprocal_ranks.append(rr)
            precisions.append(prec)

        total = len(entries)
        return RAGEvalResult(
            hit_rate=hits / total if total else 0.0,
            total_queries=total,
            hits=hits,
            mrr=sum(reciprocal_ranks) / total if total else 0.0,
            precision_at_k=sum(precisions) / total if total else 0.0,
            context_hit_rate=context_hits / total if total else 0.0,
            misses=misses,
        )

    @staticmethod
    def _match_content(
        chunk_texts: list[str], expected: list[str],
    ) -> tuple[bool, float, int]:
        """Content-based: check if any chunk contains expected snippet."""
        rr = 0.0
        relevant = 0
        for rank, text in enumerate(chunk_texts, 1):
            text_lower = text.lower()
            if any(exp.lower() in text_lower for exp in expected):
                if rr == 0.0:
                    rr = 1.0 / rank
                relevant += 1
        is_hit = relevant > 0
        prec = relevant / len(chunk_texts) if chunk_texts else 0.0
        return is_hit, rr, prec

    @staticmethod
    def _calc_rr(
        chunk_subs: list[str], expected: set[str],
    ) -> float:
        for rank, sub in enumerate(chunk_subs, 1):
            if sub in expected:
                return 1.0 / rank
        return 0.0

    @staticmethod
    def _calc_precision(
        chunk_subs: list[str], expected: set[str],
    ) -> float:
        if not chunk_subs:
            return 0.0
        return sum(1 for s in chunk_subs if s in expected) / len(chunk_subs)
