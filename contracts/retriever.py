"""Party of One — API Contract: Retriever (RAG Module).

Generated from specs in docs/specs/retriever.md. Do not edit manually.

Two components:
- Indexer: one-time indexing of Cairn SRD into ChromaDB.
- Retriever: semantic search for relevant rules, called by DM Agent
  via search_rules tool (agent-driven, not orchestrator-driven).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    """A single chunk of the Cairn SRD with metadata."""

    text: str
    section: str
    subsection: str
    chunk_id: str


@dataclass
class RetrievalResult:
    """Result of a retrieval query."""

    chunks: list[Chunk]
    query: str


class Indexer(ABC):
    """One-time indexing of Cairn SRD into a vector store.

    Reads the SRD markdown file, splits into paragraph-level chunks
    (~150-250 tokens, 20-token overlap), embeds with deepvk/USER-bge-m3,
    and stores in ChromaDB.

    Run once at deploy time, not at runtime.
    """

    @abstractmethod
    def index(self, source_path: str | Path) -> int:
        """Index the Cairn SRD file.

        Args:
            source_path: Path to data/cairn-srd-ru.md.

        Returns:
            Number of chunks indexed.

        Raises:
            FileNotFoundError: If source_path does not exist.
        """
        ...


class Retriever(ABC):
    """Semantic search for relevant Cairn rules.

    Called by DM Agent via search_rules tool when the DM needs
    rules context (combat, saves, magic, equipment, etc.).
    DM formulates the query itself based on the game situation.

    Pipeline:
    1. DM calls search_rules(query="...") during tool_use_loop.
    2. Retriever embeds query and searches ChromaDB (cosine, top-k).
    3. Chunks above min_similarity threshold are returned as tool result.
    4. DM uses the rules to make decisions.
    """

    @abstractmethod
    def search(self, query: str) -> RetrievalResult:
        """Search for relevant Cairn SRD chunks.

        Args:
            query: Free-form search query from the DM Agent.

        Returns:
            RetrievalResult with up to top_k chunks above
            min_similarity threshold. May return empty chunks
            if nothing is relevant.
        """
        ...
