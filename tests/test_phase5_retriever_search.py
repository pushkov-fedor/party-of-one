"""Phase 5: Retriever search tests.

Tests behavior described in contracts/retriever.py and docs/specs/retriever.md:

- Retriever: semantic search, top-k, min_similarity filtering
- Fallback: graceful degradation when vector store unavailable
- Property invariants: non-empty text, unique chunk_ids, etc.

These tests instantiate real ChromaDB (tmp_path) with synthetic markdown.
"""

import logging

import pytest

from contracts.retriever import Chunk, RetrievalResult


# ---------------------------------------------------------------------------
# Helper: create an indexed store with test content
# ---------------------------------------------------------------------------


@pytest.fixture
def _indexed_store(tmp_path):
    """Shared fixture: index synthetic rules into a ChromaDB store."""
    from party_of_one.rag import IndexerImpl

    store = str(tmp_path / "chroma_ret")
    indexer = IndexerImpl(vector_store_path=store)
    md = tmp_path / "rules.md"
    md.write_text(
        "# Бой\n\n## Урон\n\n"
        + "Урон снижает ОЗ цели. Спасбросок СИЛ. Критический урон. " * 5
        + "\n\n# Магия\n\n## Свитки\n\n"
        + "Свитки содержат заклинание. Эффекты причудливы. " * 5
        + "\n\n# Снаряжение\n\n## Броня\n\n"
        + "Тяжёлая броня снижает урон. Максимум 3. " * 5
        + "\n\n"
    )
    indexer.index(md)
    return store


# ---------------------------------------------------------------------------
# Retriever: contract compliance
# ---------------------------------------------------------------------------


class TestRetrieverContract:
    """Retriever.search() follows the contract in contracts/retriever.py.

    Contract:
        - search(query) -> RetrievalResult
        - Up to top_k chunks above min_similarity threshold
        - May return empty chunks if nothing is relevant
    """

    @pytest.fixture
    def retriever(self, _indexed_store):
        from party_of_one.rag import RetrieverImpl
        return RetrieverImpl(
            vector_store_path=_indexed_store,
            top_k=3, min_similarity=0.3,
        )

    def test_returns_retrieval_result(self, retriever):
        assert isinstance(retriever.search("урон бой"), RetrievalResult)

    def test_result_has_query(self, retriever):
        assert retriever.search("магия").query == "магия"

    def test_chunks_are_chunk_instances(self, retriever):
        for c in retriever.search("урон").chunks:
            assert isinstance(c, Chunk)

    def test_at_most_top_k(self, retriever):
        assert len(retriever.search("урон бой магия").chunks) <= 3

    def test_returns_chunks_for_relevant_query(self, retriever):
        assert len(retriever.search("урон спасбросок").chunks) >= 1

    def test_may_return_empty_for_irrelevant(self, retriever):
        result = retriever.search("рецепт борща")
        assert isinstance(result.chunks, list)


# ---------------------------------------------------------------------------
# Retriever: top_k parameter
# ---------------------------------------------------------------------------


class TestRetrieverTopK:
    """Retriever respects top_k. Spec: top-k=3 (default)."""

    @pytest.fixture
    def _many_store(self, tmp_path):
        from party_of_one.rag import IndexerImpl
        store = str(tmp_path / "chroma_topk")
        indexer = IndexerImpl(vector_store_path=store)
        md = tmp_path / "many.md"
        sections = [
            f"# Секция {i}\n\n"
            + "Боевые правила урон атака спасбросок. " * 10 + "\n\n"
            for i in range(10)
        ]
        md.write_text("\n".join(sections))
        indexer.index(md)
        return store

    def test_top_k_1(self, _many_store):
        from party_of_one.rag import RetrieverImpl
        r = RetrieverImpl(
            vector_store_path=_many_store, top_k=1, min_similarity=0.01,
        )
        assert len(r.search("урон бой").chunks) <= 1

    def test_top_k_5(self, _many_store):
        from party_of_one.rag import RetrieverImpl
        r = RetrieverImpl(
            vector_store_path=_many_store, top_k=5, min_similarity=0.01,
        )
        assert len(r.search("урон бой").chunks) <= 5


# ---------------------------------------------------------------------------
# Retriever: min_similarity threshold
# ---------------------------------------------------------------------------


class TestRetrieverMinSimilarity:
    """Retriever respects min_similarity. Spec: 0.3 (default)."""

    def test_high_threshold_fewer_or_no_results(self, _indexed_store):
        from party_of_one.rag import RetrieverImpl
        r = RetrieverImpl(
            vector_store_path=_indexed_store,
            top_k=3, min_similarity=0.99,
        )
        result = r.search("рецепт пирога")
        assert len(result.chunks) <= 3

    def test_low_threshold_more_results(self, _indexed_store):
        from party_of_one.rag import RetrieverImpl
        r = RetrieverImpl(
            vector_store_path=_indexed_store,
            top_k=3, min_similarity=0.01,
        )
        assert len(r.search("урон бой").chunks) >= 1


# ---------------------------------------------------------------------------
# Retriever: fallback when vector store unavailable
# ---------------------------------------------------------------------------


class TestRetrieverFallback:
    """When vector store is unavailable, retriever degrades gracefully.

    Spec (retriever.md): 'Если ChromaDB упал -- DM работает без правил.
    Пишем warning в лог.'
    """

    def test_nonexistent_store_returns_empty(self, tmp_path):
        from party_of_one.rag import RetrieverImpl
        r = RetrieverImpl(
            vector_store_path=str(tmp_path / "nonexistent"),
            top_k=3, min_similarity=0.3,
        )
        result = r.search("урон бой")
        assert isinstance(result, RetrievalResult)
        assert result.chunks == []

    def test_nonexistent_store_logs_warning(self, tmp_path, caplog):
        from party_of_one.rag import RetrieverImpl
        r = RetrieverImpl(
            vector_store_path=str(tmp_path / "nonexistent"),
            top_k=3, min_similarity=0.3,
        )
        with caplog.at_level(logging.WARNING):
            r.search("урон бой")
        warnings = [
            rec for rec in caplog.records
            if rec.levelno >= logging.WARNING
        ]
        assert len(warnings) >= 1


# ---------------------------------------------------------------------------
# Property invariants
# ---------------------------------------------------------------------------


class TestRetrieverInvariants:
    """Properties that must always hold for retriever results."""

    @pytest.fixture
    def retriever(self, _indexed_store):
        from party_of_one.rag import RetrieverImpl
        return RetrieverImpl(
            vector_store_path=_indexed_store,
            top_k=3, min_similarity=0.3,
        )

    def test_every_chunk_has_non_empty_text(self, retriever):
        for c in retriever.search("урон бой").chunks:
            assert c.text.strip()

    def test_every_chunk_has_section(self, retriever):
        for c in retriever.search("урон бой").chunks:
            assert c.section.strip()

    def test_every_chunk_has_chunk_id(self, retriever):
        for c in retriever.search("урон бой").chunks:
            assert c.chunk_id

    def test_chunk_ids_are_unique(self, retriever):
        ids = [c.chunk_id for c in retriever.search("урон магия").chunks]
        assert len(ids) == len(set(ids))

    def test_result_query_matches_input(self, retriever):
        assert retriever.search("урон спасбросок").query == "урон спасбросок"
