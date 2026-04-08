"""Phase 5: search_rules tool handler — through ToolExecutor.

Tests behavior described in:
- contracts/tools.py: ToolExecutor.execute() returns ToolCallResult
- contracts/retriever.py: Retriever.search() -> RetrievalResult with Chunk list
- docs/specs/retriever.md: DM calls search_rules as a tool, agent-driven

Covers:
- search_rules without retriever (retriever=None) -> empty result
- search_rules with retriever -> proxies chunks
- Response format (dict with query and chunks keys)
- search_rules through ToolExecutor.execute() -> ToolCallResult
- Edge cases: empty query, unicode, long query
- Batch execution with search_rules
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from contracts.retriever import Chunk, RetrievalResult
from party_of_one.memory.world_state import WorldStateDB
from party_of_one.models import ToolCallResult
from party_of_one.tools.world import ToolExecutor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    return WorldStateDB(str(tmp_path / "test.db"))


@pytest.fixture
def executor_no_retriever(db):
    """ToolExecutor without a retriever (retriever=None)."""
    return ToolExecutor(db)


@pytest.fixture
def fake_chunks():
    """A set of fake Chunk objects for testing."""
    return [
        Chunk(text="Урон снижает ОЗ цели.", section="Бой", subsection="Урон", chunk_id="c1"),
        Chunk(text="Спасбросок СИЛ.", section="Бой", subsection="Спасброски", chunk_id="c2"),
    ]


@pytest.fixture
def executor_with_retriever(db, tmp_path, fake_chunks):
    """ToolExecutor with a real indexed retriever (synthetic data)."""
    from party_of_one.rag import IndexerImpl, RetrieverImpl

    store = str(tmp_path / "chroma_tool")
    indexer = IndexerImpl(vector_store_path=store)
    md = tmp_path / "rules.md"
    md.write_text(
        "# Бой\n\n## Урон\n\n"
        + "Урон снижает ОЗ цели. Спасбросок СИЛ. Критический урон. " * 5
        + "\n\n# Магия\n\n## Свитки\n\n"
        + "Свитки содержат заклинание. Эффекты причудливы. " * 5
        + "\n\n"
    )
    indexer.index(md)
    retriever = RetrieverImpl(
        vector_store_path=store, top_k=3, min_similarity=0.01,
    )
    return ToolExecutor(db, retriever=retriever)


# ===========================================================================
# Contract compliance: search_rules returns ToolCallResult
# ===========================================================================


class TestSearchRulesContractCompliance:
    """search_rules through execute() returns a proper ToolCallResult.

    Contract: contracts/tools.py — execute() returns ToolCallResult with
    tool_name, success, result, error fields.
    """

    def test_returns_tool_call_result(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "урон"})
        assert isinstance(r, ToolCallResult)

    def test_tool_name_is_search_rules(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "урон"})
        assert r.tool_name == "search_rules"

    def test_success_is_true(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "урон"})
        assert r.success is True

    def test_error_is_none_on_success(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "урон"})
        assert r.error is None

    def test_result_is_dict(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "урон"})
        assert isinstance(r.result, dict)

    def test_result_contains_query_key(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "test"})
        assert "query" in r.result

    def test_result_contains_chunks_key(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "test"})
        assert "chunks" in r.result

    def test_result_chunks_is_list(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "test"})
        assert isinstance(r.result["chunks"], list)


# ===========================================================================
# Happy path: without retriever (retriever=None)
# ===========================================================================


class TestSearchRulesNoRetriever:
    """search_rules without retriever returns empty result.

    Spec (retriever.md): 'Если ChromaDB упал -- DM работает без правил.'
    When retriever is None, the handler gracefully returns empty chunks.
    """

    def test_empty_chunks_when_no_retriever(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "урон"})
        assert r.result["chunks"] == []

    def test_query_preserved_when_no_retriever(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "магия свитки"})
        assert r.result["query"] == "магия свитки"

    def test_success_true_when_no_retriever(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "anything"})
        assert r.success is True


# ===========================================================================
# Happy path: with retriever
# ===========================================================================


class TestSearchRulesWithRetriever:
    """search_rules with retriever proxies chunks from the retriever.

    Spec (retriever.md): DM calls search_rules(query="..."), retriever
    returns relevant chunks.
    """

    def test_returns_non_empty_chunks(self, executor_with_retriever):
        r = executor_with_retriever.execute("search_rules", {"query": "урон бой"})
        assert len(r.result["chunks"]) >= 1

    def test_query_preserved(self, executor_with_retriever):
        r = executor_with_retriever.execute("search_rules", {"query": "урон бой"})
        assert r.result["query"] == "урон бой"

    def test_chunk_has_text_key(self, executor_with_retriever):
        r = executor_with_retriever.execute("search_rules", {"query": "урон бой"})
        for chunk in r.result["chunks"]:
            assert "text" in chunk

    def test_chunk_has_section_key(self, executor_with_retriever):
        r = executor_with_retriever.execute("search_rules", {"query": "урон бой"})
        for chunk in r.result["chunks"]:
            assert "section" in chunk

    def test_chunk_has_subsection_key(self, executor_with_retriever):
        r = executor_with_retriever.execute("search_rules", {"query": "урон бой"})
        for chunk in r.result["chunks"]:
            assert "subsection" in chunk

    def test_chunk_text_is_non_empty_string(self, executor_with_retriever):
        r = executor_with_retriever.execute("search_rules", {"query": "урон бой"})
        for chunk in r.result["chunks"]:
            assert isinstance(chunk["text"], str)
            assert chunk["text"].strip()

    def test_chunk_format_is_dict_not_dataclass(self, executor_with_retriever):
        """Chunks in the result are plain dicts, not Chunk dataclasses."""
        r = executor_with_retriever.execute("search_rules", {"query": "урон бой"})
        for chunk in r.result["chunks"]:
            assert isinstance(chunk, dict)


# ===========================================================================
# Edge cases
# ===========================================================================


class TestSearchRulesEdgeCases:
    """Edge cases for search_rules: empty query, unicode, long query."""

    def test_empty_query_no_retriever(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": ""})
        assert r.success is True
        assert r.result["query"] == ""
        assert r.result["chunks"] == []

    def test_empty_query_with_retriever(self, executor_with_retriever):
        r = executor_with_retriever.execute("search_rules", {"query": ""})
        assert r.success is True
        assert isinstance(r.result["chunks"], list)

    def test_cyrillic_query(self, executor_with_retriever):
        r = executor_with_retriever.execute(
            "search_rules", {"query": "критический урон спасбросок силы"},
        )
        assert r.success is True
        assert r.result["query"] == "критический урон спасбросок силы"

    def test_long_query(self, executor_no_retriever):
        long_query = "правила боя " * 200
        r = executor_no_retriever.execute("search_rules", {"query": long_query})
        assert r.success is True
        assert r.result["query"] == long_query

    def test_whitespace_only_query(self, executor_no_retriever):
        r = executor_no_retriever.execute("search_rules", {"query": "   "})
        assert r.success is True
        assert r.result["query"] == "   "


# ===========================================================================
# Business rules: read-only, no DB mutation
# ===========================================================================


class TestSearchRulesReadOnly:
    """search_rules is a read-only operation -- no world state changes.

    Spec (retriever.md): search_rules only returns rules, does not
    modify world state.
    """

    def test_no_db_mutation(self, db, executor_no_retriever):
        snapshot_before = db.snapshot()
        executor_no_retriever.execute("search_rules", {"query": "урон"})
        snapshot_after = db.snapshot()
        assert snapshot_before == snapshot_after


# ===========================================================================
# Batch execution with search_rules
# ===========================================================================


class TestSearchRulesInBatch:
    """search_rules can be used inside execute_batch alongside other tools.

    Spec: search_rules is read-only (like roll_dice, get_entity).
    """

    def test_batch_with_search_rules_and_roll_dice(self, executor_no_retriever):
        cmds = [
            {"name": "search_rules", "args": {"query": "урон"}},
            {"name": "roll_dice", "args": {"sides": 6, "count": 1}},
        ]
        results = executor_no_retriever.execute_batch(cmds)
        assert len(results) == 2
        assert results[0].tool_name == "search_rules"
        assert results[0].success is True
        assert results[1].tool_name == "roll_dice"
        assert results[1].success is True

    def test_batch_search_rules_only(self, executor_no_retriever):
        cmds = [
            {"name": "search_rules", "args": {"query": "магия"}},
            {"name": "search_rules", "args": {"query": "бой"}},
        ]
        results = executor_no_retriever.execute_batch(cmds)
        assert len(results) == 2
        assert all(r.success for r in results)
        assert results[0].result["query"] == "магия"
        assert results[1].result["query"] == "бой"
