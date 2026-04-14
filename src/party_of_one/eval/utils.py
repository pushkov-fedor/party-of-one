"""Shared utilities for eval pipeline."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dicts."""
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response, handling markdown code blocks.

    Returns parsed dict or None if parsing fails.
    """
    if not text or not text.strip():
        return None

    cleaned = extract_json(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def extract_json(text: str) -> str:
    """Extract JSON from LLM response.

    Handles: raw JSON, ```json ... ```, ``` ... ```,
    or JSON embedded in surrounding text.
    """
    text = text.strip()

    if text.startswith("{"):
        return text

    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]

    return text
