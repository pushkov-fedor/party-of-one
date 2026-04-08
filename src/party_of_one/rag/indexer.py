"""Indexer — one-time indexing of Cairn SRD into ChromaDB."""

from __future__ import annotations

import re
from pathlib import Path

from contracts.retriever import Indexer as IndexerContract

from party_of_one.config import RAGConfig
from party_of_one.logger import get_logger

logger = get_logger()


def _split_into_chunks(
    text: str,
    max_tokens: int = 200,
    overlap_tokens: int = 20,
) -> list[dict]:
    """Split markdown text into paragraph-level chunks with metadata."""
    chunks = []
    current_section = ""
    current_subsection = ""

    paragraphs = re.split(r"\n\n+", text.strip())

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if para.startswith("### "):
            current_subsection = para.lstrip("# ").strip()
            continue
        if para.startswith("## "):
            current_subsection = para.lstrip("# ").strip()
            continue
        if para.startswith("# "):
            current_section = para.lstrip("# ").strip()
            current_subsection = ""
            continue

        words = para.split()
        if len(words) < 1:
            continue

        estimated_tokens = int(len(words) * 1.5)

        if estimated_tokens <= max_tokens:
            chunks.append({
                "text": para,
                "section": current_section,
                "subsection": current_subsection,
            })
        else:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current_chunk_words: list[str] = []
            for sentence in sentences:
                s_words = sentence.split()
                if len(current_chunk_words) + len(s_words) > max_tokens // 1.5:
                    if current_chunk_words:
                        chunks.append({
                            "text": " ".join(current_chunk_words),
                            "section": current_section,
                            "subsection": current_subsection,
                        })
                        overlap_words = int(overlap_tokens / 1.5)
                        current_chunk_words = current_chunk_words[-overlap_words:]
                current_chunk_words.extend(s_words)
            if current_chunk_words:
                chunks.append({
                    "text": " ".join(current_chunk_words),
                    "section": current_section,
                    "subsection": current_subsection,
                })

    return chunks


class Indexer(IndexerContract):
    """Indexes Cairn SRD markdown into ChromaDB with manual embeddings."""

    def __init__(self, config: RAGConfig | None = None, vector_store_path: str = ""):
        if config:
            self._vector_store_path = config.vector_store_path
            self._model_name = config.embedding_model
        else:
            self._vector_store_path = vector_store_path
            self._model_name = "deepvk/USER-bge-m3"

    def index(self, source_path: str | Path) -> int:
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"SRD file not found: {source_path}")

        text = source_path.read_text(encoding="utf-8")
        if not text.strip():
            return 0

        raw_chunks = _split_into_chunks(text)
        if not raw_chunks:
            return 0

        from sentence_transformers import SentenceTransformer
        import chromadb

        model = SentenceTransformer(self._model_name)
        documents = [c["text"] for c in raw_chunks]
        embeddings = model.encode(documents, normalize_embeddings=True).tolist()

        client = chromadb.PersistentClient(path=self._vector_store_path)
        try:
            client.delete_collection("cairn_srd")
        except Exception:
            pass

        collection = client.create_collection(
            name="cairn_srd",
            metadata={"hnsw:space": "cosine"},
        )

        ids = [f"chunk_{i}" for i in range(len(raw_chunks))]
        metadatas = [{"section": c["section"], "subsection": c["subsection"]}
                     for c in raw_chunks]

        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info("indexer_complete", chunks=len(raw_chunks),
                     source=str(source_path))
        return len(raw_chunks)
