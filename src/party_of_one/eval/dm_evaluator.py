"""DM agent evaluator — single session-level LLM judge."""

from __future__ import annotations

import json
from typing import Any, Callable

from contracts.eval import DMEvaluator
from contracts.eval_models import DMEvalResult

from party_of_one.eval.utils import parse_json_response
from party_of_one.logger import get_logger
from party_of_one.prompts import get_prompt

logger = get_logger()


class DMEvaluatorImpl(DMEvaluator):
    """Session-level DM evaluation — one LLM call scoring 5 criteria (1-5).

    Criteria: consistency, rules, adaptivity, plot_progression, repetition.
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
    ) -> DMEvalResult:
        dm_turns = [
            e for e in session_log
            if e.get("event") == "llm_call"
            and e.get("agent") == "dm"
            and e.get("dm_response")
        ]
        total = len(dm_turns)

        scores = self._session_judge(session_log)

        return DMEvalResult(
            rule_compliance=scores.get("rules", 0) / 5.0,
            total_turns=total,
            consistency=scores.get("consistency", 0),
            rules_score=scores.get("rules", 0),
            adaptivity=scores.get("adaptivity", 0),
            plot_progression=scores.get("plot_progression", 0),
            repetition=scores.get("repetition", 0),
            llm_issues=scores.get("issues", []),
            llm_highlights=scores.get("highlights", []),
        )

    def _session_judge(
        self, session_log: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Single LLM call evaluating the full session."""
        session_text = self._format_session(session_log)
        if not session_text:
            return {}

        prompt = get_prompt("eval_dm_session").format(
            session_log=session_text,
        )

        raw = self._call_llm(prompt)
        result = parse_json_response(raw)
        if result is None:
            logger.warning("dm_session_judge_parse_error", raw=raw[:300])
            return {}

        scores = result.get("scores", {})
        scores["issues"] = result.get("issues", [])
        scores["highlights"] = result.get("highlights", [])
        return scores

    @staticmethod
    def _format_session(session_log: list[dict[str, Any]]) -> str:
        """Format session log with world state snapshots for the judge."""
        parts: list[str] = []
        current_round = 0

        for entry in session_log:
            if entry.get("event") != "llm_call":
                continue

            r = entry.get("round", 0)
            if r != current_round:
                current_round = r
                snapshot = entry.get("world_state_snapshot", "")
                if snapshot:
                    lines = snapshot.split("\n")
                    short = "\n".join(lines[:30])
                    parts.append(f"\n--- Раунд {r} ---")
                    parts.append(f"[Состояние мира]\n{short}")

            agent = entry.get("agent", "")
            if agent == "dm" and entry.get("dm_response"):
                cmds = entry.get("commands", [])
                cmd_str = ", ".join(
                    f"{c['name']}({json.dumps(c.get('args', {}), ensure_ascii=False)})"
                    for c in cmds if c.get("name")
                )
                line = f"DM: {entry['dm_response']}"
                if cmd_str:
                    line += f"\n  [команды: {cmd_str}]"
                parts.append(line)
            elif agent == "companion" and entry.get("companion_action"):
                name = entry.get("companion_name", "Companion")
                parts.append(f"{name}: {entry['companion_action']}")

        return "\n\n".join(parts)

    def _call_llm(self, prompt: str) -> str:
        if self._judge is not None:
            score = self._judge.evaluate(prompt)
            return score.raw_response or score.explanation
        if self._llm_call is not None:
            return self._llm_call(prompt)
        msg = "DMEvaluatorImpl requires either judge or llm_call"
        raise RuntimeError(msg)
