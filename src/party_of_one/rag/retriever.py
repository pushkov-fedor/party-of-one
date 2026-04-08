"""Retriever — semantic search over Cairn SRD via ChromaDB."""

from __future__ import annotations

import logging as _stdlib_logging

from contracts.retriever import (
    Retriever as RetrieverContract,
    RetrievalResult,
    Chunk,
)

from party_of_one.config import RAGConfig
from party_of_one.logger import get_logger

logger = get_logger()
_stdlib_logger = _stdlib_logging.getLogger(__name__)


class Retriever(RetrieverContract):
    """Semantic search over Cairn SRD via ChromaDB with manual embeddings.

    Called by DM Agent via search_rules tool during tool_use_loop.
    """

    def __init__(
        self,
        config: RAGConfig | None = None,
        vector_store_path: str = "",
        top_k: int = 3,
        min_similarity: float = 0.3,
    ):
        if config:
            self._vector_store_path = config.vector_store_path
            self._top_k = config.top_k
            self._min_similarity = config.min_similarity
            self._model_name = config.embedding_model
        else:
            self._vector_store_path = vector_store_path
            self._top_k = top_k
            self._min_similarity = min_similarity
            self._model_name = "deepvk/USER-bge-m3"
        self._collection = None
        self._model = None
        self._load_attempted = False

    def _ensure_loaded(self):
        if self._collection is not None or self._load_attempted:
            return
        self._load_attempted = True
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            client = chromadb.PersistentClient(path=self._vector_store_path)
            self._collection = client.get_collection("cairn_srd")
            self._model = SentenceTransformer(self._model_name)
            logger.info("retriever_loaded", path=self._vector_store_path)
        except Exception as e:
            logger.warning("retriever_unavailable", error=str(e))
            _stdlib_logger.warning("retriever_unavailable: %s", e)
            self._collection = None

    def search(self, query: str) -> RetrievalResult:
        self._ensure_loaded()

        if self._collection is None or self._model is None:
            logger.warning("retriever_fallback", reason="vector store unavailable")
            _stdlib_logger.warning("retriever_fallback: vector store unavailable")
            return RetrievalResult(chunks=[], query=query)

        try:
            query_embedding = self._model.encode(
                [query], normalize_embeddings=True,
            ).tolist()

            results = self._collection.query(
                query_embeddings=query_embedding,
                n_results=self._top_k,
            )
        except Exception as e:
            logger.warning("retriever_search_error", error=str(e))
            return RetrievalResult(chunks=[], query=query)

        chunks = []
        if results and results["documents"]:
            docs = results["documents"][0]
            metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
            distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
            ids = results["ids"][0] if results.get("ids") else [f"chunk_{i}" for i in range(len(docs))]

            for doc, meta, dist, chunk_id in zip(docs, metadatas, distances, ids):
                similarity = 1.0 - dist
                if similarity < self._min_similarity:
                    continue
                chunks.append(Chunk(
                    text=doc,
                    section=meta.get("section", ""),
                    subsection=meta.get("subsection", ""),
                    chunk_id=chunk_id,
                ))

        return RetrievalResult(chunks=chunks, query=query)
