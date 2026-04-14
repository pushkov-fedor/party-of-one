"""Holistic session evaluator — narrative-only LLM-as-judge."""

from __future__ import annotations

import json
from typing import Any

from contracts.eval import HolisticEvaluator, LLMJudge
from contracts.eval_models import HolisticEvalResult, JudgeScore

from party_of_one.prompts import get_prompt


class HolisticEvaluatorImpl(HolisticEvaluator):
    """Evaluates an entire session as a narrative.

    Filters log to narrative-only: removes tool_use, commands,
    technical events. Judge sees only the story.
    """

    def __init__(self, *, judge: LLMJudge) -> None:
        self._judge = judge

    def evaluate(
        self, session_log: list[dict[str, Any]],
    ) -> HolisticEvalResult:
        narrative = self._extract_narrative(session_log)
        if not narrative:
            empty = JudgeScore(scores={}, explanation="no narrative data")
            return HolisticEvalResult(scores=empty)

        prompt = get_prompt("eval_holistic").format(narrative=narrative)
        try:
            score = self._judge.evaluate(prompt)
        except RuntimeError:
            fallback = JudgeScore(
                scores={}, explanation="judge failed to return valid JSON",
            )
            return HolisticEvalResult(scores=fallback, issues=["judge_error"])

        highlights, issues = self._extract_lists(score.raw_response)

        return HolisticEvalResult(
            scores=score,
            highlights=highlights,
            issues=issues,
        )

    @staticmethod
    def _extract_narrative(log: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for entry in log:
            event = entry.get("event", "")
            if event == "tool_use":
                continue
            agent = entry.get("agent", "")
            if agent == "dm" and entry.get("dm_response"):
                parts.append(f"DM: {entry['dm_response']}")
            elif agent == "companion" and entry.get("companion_action"):
                name = entry.get("companion_name", "Companion")
                parts.append(f"{name}: {entry['companion_action']}")
        return "\n\n".join(parts)

    @staticmethod
    def _extract_lists(raw: str) -> tuple[list[str], list[str]]:
        try:
            data = json.loads(raw)
            return data.get("highlights", []), data.get("issues", [])
        except (json.JSONDecodeError, TypeError):
            return [], []
