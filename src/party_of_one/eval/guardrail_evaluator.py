"""Guardrails embedding layer evaluator — deterministic, no LLM."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contracts.eval import GuardrailEvaluator
from contracts.eval_models import GuardrailEvalResult
from contracts.guardrails import PreLLMGuardrail

from party_of_one.eval.utils import load_jsonl


class GuardrailEvaluatorImpl(GuardrailEvaluator):
    """Runs golden inputs through the embedding guardrail layer.

    Computes true-positive rate (injections caught) and
    false-positive rate (legitimate inputs blocked).
    """

    def __init__(self, *, guardrail: PreLLMGuardrail) -> None:
        self._guardrail = guardrail

    def evaluate(self, dataset_path: str | Path) -> GuardrailEvalResult:
        entries = load_jsonl(dataset_path)

        injections: list[str] = []
        legitimate: list[str] = []
        false_negatives: list[str] = []
        false_positives: list[str] = []

        for entry in entries:
            inp = entry["input"]
            expected = entry["expected"]  # "blocked" | "passed"
            result = self._guardrail.check_embedding(inp)
            actually_blocked = not result.passed

            if expected == "blocked":
                injections.append(inp)
                if not actually_blocked:
                    false_negatives.append(inp)
            else:
                legitimate.append(inp)
                if actually_blocked:
                    false_positives.append(inp)

        total_inj = len(injections)
        total_leg = len(legitimate)
        caught = total_inj - len(false_negatives)

        return GuardrailEvalResult(
            true_positive_rate=caught / total_inj if total_inj else 0.0,
            false_positive_rate=(
                len(false_positives) / total_leg if total_leg else 0.0
            ),
            total_injections=total_inj,
            total_legitimate=total_leg,
            false_negatives=false_negatives,
            false_positives=false_positives,
        )


