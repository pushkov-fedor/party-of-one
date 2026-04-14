"""Prompt registry — loads versioned prompts from data/prompts.yml.

Usage:
    from party_of_one.prompts import get_prompt

    # Get active version
    prompt = get_prompt("dm_system")

    # Get specific version
    prompt_v1 = get_prompt("dm_system", version=1)

    # Check version info
    info = get_prompt_info("dm_system")
    # -> {"active_version": 2, "versions": [1, 2]}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PROMPTS_PATH = Path(__file__).parent.parent.parent / "data" / "prompts.yml"

_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        with open(_PROMPTS_PATH, encoding="utf-8") as f:
            _cache = yaml.safe_load(f)
    return _cache


def reload() -> None:
    """Force reload from disk (useful after editing prompts.yml)."""
    global _cache
    _cache = None
    _load()


def get_prompt(name: str, version: int | None = None) -> str:
    """Return prompt text by name.

    Args:
        name: Prompt name as defined in prompts.yml.
        version: Specific version number. If None, returns active version.

    Returns:
        Prompt text (with {placeholders} for .format()).

    Raises:
        KeyError: If prompt name or version not found.
    """
    data = _load()
    prompts = data["prompts"]

    if name not in prompts:
        available = sorted(prompts.keys())
        raise KeyError(f"Unknown prompt {name!r}. Available: {available}")

    prompt_data = prompts[name]

    if version is None:
        version = prompt_data["active_version"]

    versions = prompt_data["versions"]
    if version not in versions:
        available = sorted(versions.keys())
        raise KeyError(
            f"Prompt {name!r} has no version {version}. "
            f"Available: {available}"
        )

    return versions[version]["text"]


def get_prompt_info(name: str) -> dict[str, Any]:
    """Return metadata about a prompt (versions, dates, changelogs)."""
    data = _load()
    prompt_data = data["prompts"][name]
    return {
        "description": prompt_data.get("description", ""),
        "active_version": prompt_data["active_version"],
        "versions": [
            {
                "version": v,
                "date": info.get("date", ""),
                "changelog": info.get("changelog", ""),
            }
            for v, info in sorted(prompt_data["versions"].items())
        ],
    }


def list_prompts() -> list[str]:
    """Return all prompt names."""
    data = _load()
    return sorted(data["prompts"].keys())
