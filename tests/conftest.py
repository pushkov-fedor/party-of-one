"""Shared fixtures for the test suite.

Key design decision: Pre-LLM guardrail uses two detection layers:
1. Regex filter with normalization (fast, <1ms)
2. Embedding similarity via deepvk/USER-bge-m3 (slow, ~600MB model load)

For unit tests that exercise regex behavior, we patch check_embedding
to skip the model entirely. This keeps tests fast (~1-2s total).

For integration tests that need the real embedding layer, use the
``embedding`` marker: ``pytest -m embedding``.

To exclude slow embedding tests: ``pytest -m "not embedding"``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from contracts.guardrails import GuardrailResult


# ---------------------------------------------------------------------------
# Pre-LLM guardrail: regex-only (no embedding model)
# ---------------------------------------------------------------------------

@pytest.fixture
def pre_llm_guardrail():
    """PreLLMGuardrailImpl with embedding layer stubbed out.

    check() runs regex normalization + pattern matching as usual,
    but check_embedding() always returns passed=True so the 600MB
    model is never loaded.
    """
    from party_of_one.guardrails.pre_llm import PreLLMGuardrailImpl

    guardrail = PreLLMGuardrailImpl()
    with patch.object(
        guardrail,
        "check_embedding",
        return_value=GuardrailResult(passed=True),
    ):
        yield guardrail


# ---------------------------------------------------------------------------
# Pre-LLM guardrail: real embedding (session-scoped, loads model once)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pre_llm_guardrail_with_embedding():
    """PreLLMGuardrailImpl with real embedding model.

    Session-scoped: the ~600MB model loads once per test run.
    Only used by tests marked with ``@pytest.mark.embedding``.
    """
    from party_of_one.guardrails.pre_llm import PreLLMGuardrailImpl

    return PreLLMGuardrailImpl()


# ---------------------------------------------------------------------------
# Post-LLM guardrail (no heavy dependencies, no special handling needed)
# ---------------------------------------------------------------------------

@pytest.fixture
def post_llm_guardrail():
    """PostLLMGuardrailImpl for leak detection tests."""
    from party_of_one.guardrails.post_llm import PostLLMGuardrailImpl

    return PostLLMGuardrailImpl()
