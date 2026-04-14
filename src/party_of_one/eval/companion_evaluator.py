"""Companion agent evaluator — batched per-companion LLM judge."""

from __future__ import annotations

from typing import Any, Callable

from contracts.eval import CompanionEvaluator
from contracts.eval_models import CompanionEvalResult, CompanionScores

from party_of_one.eval.utils import parse_json_response
from party_of_one.logger import get_logger
from party_of_one.prompts import get_prompt

logger = get_logger()


class CompanionEvaluatorImpl(CompanionEvaluator):
    """Batched companion evaluation — one LLM call per companion.

    Groups all actions by companion, sends each companion's full
    action list to the judge in one call. Scores: in_character,
    agency, liveliness, action_variety (1-5 each).
    """

    def __init__(
        self,
        *,
        judge: Any | None = None,
        llm_call: Callable[[str], str] | None = None,
    ) -> None:
        self._judge = judge
        self._llm_call = llm_call

    def evaluate(
        self, session_log: list[dict[str, Any]],
    ) -> CompanionEvalResult:
        grouped = self._group_by_companion(session_log)
        if not grouped:
            return CompanionEvalResult(companions=[], total_turns=0)

        total = sum(len(actions) for actions in grouped.values())
        companions: list[CompanionScores] = []

        for name, entries in grouped.items():
            scores = self._judge_companion(name, entries)
            companions.append(scores)

        return CompanionEvalResult(companions=companions, total_turns=total)

    @staticmethod
    def _group_by_companion(
        session_log: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Group companion turns by name."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for entry in session_log:
            if (
                entry.get("event") == "llm_call"
                and entry.get("agent") == "companion"
                and entry.get("companion_action")
            ):
                name = entry.get("companion_name", "Unknown")
                grouped.setdefault(name, []).append(entry)
        return grouped

    def _judge_companion(
        self, name: str, entries: list[dict[str, Any]],
    ) -> CompanionScores:
        """One LLM call for all actions of one companion."""
        profile = entries[0].get("personality_profile", "")

        action_lines: list[str] = []
        for entry in entries:
            r = entry.get("round", "?")
            action_lines.append(f"[Раунд {r}] {entry['companion_action']}")
        all_actions = "\n\n".join(action_lines)

        prompt = get_prompt("eval_companion").format(
            personality_profile=profile,
            name=name,
            all_actions=all_actions,
        )

        raw = self._call_llm(prompt)
        result = parse_json_response(raw)
        if result is None:
            logger.warning("companion_judge_parse_error", name=name,
                           raw=raw[:300])
            return CompanionScores(name=name)

        scores = result.get("scores", {})
        return CompanionScores(
            name=name,
            in_character=scores.get("in_character", 0),
            agency=scores.get("agency", 0),
            liveliness=scores.get("liveliness", 0),
            action_variety=scores.get("action_variety", 0),
            issues=result.get("issues", []),
            highlights=result.get("highlights", []),
        )

    def _call_llm(self, prompt: str) -> str:
        if self._judge is not None:
            score = self._judge.evaluate(prompt)
            return score.raw_response or score.explanation
        if self._llm_call is not None:
            return self._llm_call(prompt)
        msg = "CompanionEvaluatorImpl requires either judge or llm_call"
        raise RuntimeError(msg)
