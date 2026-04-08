"""Phase 5: Retriever (RAG Module) — data models.

Tests behavior described in contracts/retriever.py and docs/specs/retriever.md:

- Chunk / RetrievalResult dataclass contract compliance

All tests are behavior-driven from specs, not from implementation.
"""

from contracts.retriever import Chunk, RetrievalResult


# ---------------------------------------------------------------------------
# Contract compliance: data models
# ---------------------------------------------------------------------------


class TestChunkDataModel:
    """Chunk dataclass has required fields per contracts/retriever.py."""

    def test_chunk_has_text_field(self):
        c = Chunk(text="some text", section="Combat", subsection="Damage", chunk_id="c1")
        assert c.text == "some text"

    def test_chunk_has_section_and_subsection(self):
        c = Chunk(text="t", section="Magic", subsection="Scrolls", chunk_id="c2")
        assert c.section == "Magic"
        assert c.subsection == "Scrolls"

    def test_chunk_has_chunk_id(self):
        c = Chunk(text="t", section="s", subsection="ss", chunk_id="unique-id-42")
        assert c.chunk_id == "unique-id-42"


class TestRetrievalResultDataModel:
    """RetrievalResult dataclass per contracts/retriever.py."""

    def test_result_has_chunks_and_query(self):
        r = RetrievalResult(chunks=[], query="test query")
        assert isinstance(r.chunks, list)
        assert r.query == "test query"

    def test_result_with_empty_chunks(self):
        r = RetrievalResult(chunks=[], query="nothing relevant")
        assert r.chunks == []

    def test_result_with_multiple_chunks(self):
        chunks = [
            Chunk(text="a", section="s1", subsection="ss1", chunk_id="c1"),
            Chunk(text="b", section="s2", subsection="ss2", chunk_id="c2"),
        ]
        r = RetrievalResult(chunks=chunks, query="q")
        assert len(r.chunks) == 2
