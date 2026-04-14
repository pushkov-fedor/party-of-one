"""Compressor quality evaluator — uses LLM-as-judge."""

from __future__ import annotations

from typing import Any

from contracts.eval import CompressorEvaluator, LLMJudge
from contracts.eval_models import CompressorEvalResult, JudgeScore

from party_of_one.prompts import get_prompt


class CompressorEvaluatorImpl(CompressorEvaluator):
    """Evaluates compression quality from session log events.

    Extracts compression events, sends each to LLM judge.
    For multi-compression, evaluates each cycle separately.
    """

    def __init__(self, *, judge: LLMJudge) -> None:
        self._judge = judge

    def evaluate(
        self, session_log: list[dict[str, Any]],
    ) -> CompressorEvalResult:
        compressions = [
            e for e in session_log if e.get("event") == "compression"
        ]

        if not compressions:
            empty = JudgeScore(scores={}, explanation="no compression events")
            return CompressorEvalResult(single_compression=empty)

        first = self._judge_compression(compressions[0])

        multi: list[JudgeScore] = []
        if len(compressions) > 1:
            multi = [self._judge_compression(c) for c in compressions]

        return CompressorEvalResult(
            single_compression=first,
            multi_compression=multi,
        )

    def _judge_compression(self, event: dict[str, Any]) -> JudgeScore:
        prompt = get_prompt("eval_compressor").format(
            raw_history=event.get("raw_history", ""),
            compressed_history=event.get("compressed_history", ""),
            world_state_snapshot=event.get("world_state_snapshot", ""),
        )
        try:
            return self._judge.evaluate(prompt)
        except RuntimeError:
            return JudgeScore(
                scores={}, explanation="judge failed to return valid JSON",
            )
