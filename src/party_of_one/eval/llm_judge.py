"""LLM-as-judge: sends evaluation prompt to LLM, parses JSON response."""

from __future__ import annotations

import json
from typing import Callable

from contracts.eval import LLMJudge
from contracts.eval_models import JudgeScore

from party_of_one.eval.utils import extract_json


class LLMJudgeImpl(LLMJudge):
    """Concrete LLM judge backed by a callable that returns raw text.

    Args:
        llm_call: Callable that takes a prompt string and returns
            the LLM response text. Allows easy mocking in tests
            and flexible wiring to any LLM backend.
    """

    def __init__(self, *, llm_call: Callable[[str], str]) -> None:
        self._llm_call = llm_call

    def evaluate(self, prompt: str) -> JudgeScore:
        raw = self._llm_call(prompt)
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> JudgeScore:
        if not raw or not raw.strip():
            msg = "Judge LLM returned empty response"
            raise RuntimeError(msg)

        # Try to extract JSON from markdown code blocks
        cleaned = extract_json(raw)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            msg = f"Judge LLM returned invalid JSON: {exc}"
            raise RuntimeError(msg) from exc

        if "scores" not in data:
            msg = "Judge response missing 'scores' key"
            raise RuntimeError(msg)

        return JudgeScore(
            scores=data["scores"],
            explanation=data.get("explanation", ""),
            raw_response=raw,
        )


