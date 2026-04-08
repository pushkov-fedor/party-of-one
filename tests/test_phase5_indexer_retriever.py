"""Phase 5: Indexer tests.

Tests behavior described in contracts/retriever.py and docs/specs/retriever.md:

- Indexer: reads markdown, splits into chunks, stores in ChromaDB
- Chunking: paragraph-level, ~150-250 tokens, overlap 20
- Real SRD file produces reasonable chunk count

These tests instantiate real ChromaDB (tmp_path) with synthetic markdown.
"""

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Indexer: contract compliance
# ---------------------------------------------------------------------------


class TestIndexerContract:
    """Indexer.index() follows the contract in contracts/retriever.py.

    Contract:
        - index(source_path) -> int (number of chunks indexed)
        - Raises FileNotFoundError if source_path does not exist
    """

    @pytest.fixture
    def indexer(self, tmp_path):
        from party_of_one.rag import IndexerImpl
        return IndexerImpl(
            vector_store_path=str(tmp_path / "chroma_test"),
        )

    def test_index_returns_int(self, indexer, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nSome content here.\n")
        assert isinstance(indexer.index(md_file), int)

    def test_index_returns_positive_for_nonempty(self, indexer, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "# Section\n\n"
            + "Paragraph with content to form a chunk. " * 10
        )
        assert indexer.index(md_file) > 0

    def test_index_raises_file_not_found_string(self, indexer):
        with pytest.raises(FileNotFoundError):
            indexer.index("/nonexistent/path/file.md")

    def test_index_raises_file_not_found_path(self, indexer):
        with pytest.raises(FileNotFoundError):
            indexer.index(Path("/nonexistent/path.md"))

    def test_index_accepts_string_path(self, indexer, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nContent.\n")
        assert isinstance(indexer.index(str(md_file)), int)

    def test_index_accepts_path_object(self, indexer, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n\nContent.\n")
        assert isinstance(indexer.index(md_file), int)


# ---------------------------------------------------------------------------
# Indexer: chunking behavior
# ---------------------------------------------------------------------------


class TestIndexerChunking:
    """Indexer splits markdown into paragraph-level chunks.

    Spec (retriever.md):
        - Paragraph-level splitting
        - Chunk size: ~150-250 tokens
        - Overlap: 20 tokens
        - Metadata: {section, subsection}
    """

    @pytest.fixture
    def indexer(self, tmp_path):
        from party_of_one.rag import IndexerImpl
        return IndexerImpl(
            vector_store_path=str(tmp_path / "chroma_chunk"),
        )

    def test_multiple_sections_produce_multiple_chunks(self, indexer, tmp_path):
        md_file = tmp_path / "multi.md"
        md_file.write_text(
            "# Section A\n\n"
            + "Content for section A. " * 50 + "\n\n"
            "## Subsection A1\n\n"
            + "Content for subsection A1. " * 50 + "\n\n"
            "# Section B\n\n"
            + "Content for section B. " * 50 + "\n\n"
        )
        assert indexer.index(md_file) >= 2

    def test_empty_markdown_produces_zero_chunks(self, indexer, tmp_path):
        md_file = tmp_path / "empty.md"
        md_file.write_text("")
        assert indexer.index(md_file) == 0

    def test_short_markdown_produces_at_least_one_chunk(self, indexer, tmp_path):
        md_file = tmp_path / "short.md"
        md_file.write_text("# Title\n\nShort paragraph.\n")
        assert indexer.index(md_file) >= 1


# ---------------------------------------------------------------------------
# Indexer: real SRD file
# ---------------------------------------------------------------------------


class TestIndexerWithRealSRD:
    """Indexer processes the actual Cairn SRD file (~15 pages)."""

    @pytest.fixture
    def indexer(self, tmp_path):
        from party_of_one.rag import IndexerImpl
        return IndexerImpl(
            vector_store_path=str(tmp_path / "chroma_srd"),
        )

    @pytest.fixture
    def srd_path(self):
        path = Path("data/cairn-srd-ru.md")
        if not path.exists():
            pytest.skip("Cairn SRD not found")
        return path

    def test_srd_produces_many_chunks(self, indexer, srd_path):
        count = indexer.index(srd_path)
        assert count >= 10

    def test_srd_chunk_count_upper_bound(self, indexer, srd_path):
        count = indexer.index(srd_path)
        assert count <= 500
