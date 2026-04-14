"""Indexer — one-time indexing of Cairn SRD into ChromaDB."""

from __future__ import annotations

import json
import re
from pathlib import Path

from contracts.retriever import Indexer as IndexerContract

from party_of_one.config import RAGConfig
from party_of_one.logger import get_logger

logger = get_logger()

# ── Chunking ──────────────────────────────────────────────────────────────

_MAX_TOKENS = 400  # ~260 words
_OVERLAP_TOKENS = 50

# Sections to exclude from indexing (summaries that duplicate main content)
_EXCLUDED_SECTIONS = {"Краткие правила"}


def _split_into_chunks(
    text: str,
    max_tokens: int = _MAX_TOKENS,
    overlap_tokens: int = _OVERLAP_TOKENS,
) -> list[dict]:
    """Split markdown into heading-based chunks with header prepending.

    Strategy:
    1. Each subsection = one chunk (never merge across subsections).
    2. Prepend heading path to chunk text for better embedding.
    3. Long subsections split by sentences with overlap.
    4. Bestiary split by individual monster entries.
    5. Excluded sections (Краткие правила) are skipped.
    """
    sections = _extract_sections(text)
    chunks = []

    for sec in sections:
        if sec["subsection"] in _EXCLUDED_SECTIONS:
            continue

        header_prefix = sec["header_path"]
        body = sec["body"].strip()
        if not body:
            continue

        # Special handling: bestiary — split by individual monsters
        if sec["subsection"] == "Бестиарий":
            for mc in _split_bestiary(body, sec, header_prefix):
                chunks.append(mc)
            continue

        full_text = f"{header_prefix}\n\n{body}" if header_prefix else body
        est_tokens = int(len(full_text.split()) * 1.5)

        if est_tokens <= max_tokens:
            chunks.append({
                "text": full_text,
                "section": sec["section"],
                "subsection": sec["subsection"],
                "header_path": header_prefix,
            })
        else:
            for part in _split_by_sentences(body, max_tokens, overlap_tokens):
                part_text = (
                    f"{header_prefix}\n\n{part}" if header_prefix else part
                )
                chunks.append({
                    "text": part_text,
                    "section": sec["section"],
                    "subsection": sec["subsection"],
                    "header_path": header_prefix,
                })

    return chunks


def _extract_sections(text: str) -> list[dict]:
    """Parse markdown into sections with heading hierarchy."""
    sections: list[dict] = []
    h1 = h2 = h3 = ""
    current_body_lines: list[str] = []
    current_subsection = ""

    def _flush():
        body = "\n".join(current_body_lines).strip()
        if body:
            parts = [p for p in [h1, h2, h3] if p]
            sections.append({
                "section": h1,
                "subsection": current_subsection or h2 or h1,
                "header_path": " > ".join(parts),
                "body": body,
            })

    for line in text.split("\n"):
        stripped = line.strip()

        if stripped.startswith("#### "):
            _flush()
            current_body_lines = []
            h3 = stripped.lstrip("# ").strip()
            current_subsection = h3
        elif stripped.startswith("### "):
            _flush()
            current_body_lines = []
            h3 = stripped.lstrip("# ").strip()
            current_subsection = h3
        elif stripped.startswith("## "):
            _flush()
            current_body_lines = []
            h2 = stripped.lstrip("# ").strip()
            h3 = ""
            current_subsection = h2
        elif stripped.startswith("# "):
            _flush()
            current_body_lines = []
            h1 = stripped.lstrip("# ").strip()
            h2 = h3 = ""
            current_subsection = ""
        else:
            current_body_lines.append(line)

    _flush()
    return sections


def _split_bestiary(
    body: str, sec: dict, header_prefix: str,
) -> list[dict]:
    """Split bestiary into individual monster entries."""
    monsters = re.split(r"\n(?=\*\*[А-ЯA-Z])", body)
    chunks = []
    for monster in monsters:
        monster = monster.strip()
        if not monster or len(monster.split()) < 5:
            continue
        # Extract monster name for better header
        name_match = re.match(r"\*\*(.+?)\*\*", monster)
        name = name_match.group(1) if name_match else "Монстр"
        full = f"{header_prefix} > {name}\n\n{monster}"
        chunks.append({
            "text": full,
            "section": sec["section"],
            "subsection": sec["subsection"],
            "header_path": f"{header_prefix} > {name}",
        })
    return chunks


def _split_by_sentences(
    text: str, max_tokens: int, overlap_tokens: int,
) -> list[str]:
    """Split text by sentences respecting token limit, no overlap."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    parts: list[str] = []
    current_words: list[str] = []

    for sentence in sentences:
        s_words = sentence.split()
        est = int((len(current_words) + len(s_words)) * 1.5)
        if est > max_tokens and current_words:
            parts.append(" ".join(current_words))
            current_words = []
        current_words.extend(s_words)

    if current_words:
        parts.append(" ".join(current_words))
    return parts


def export_chunks_jsonl(chunks: list[dict], path: str | Path) -> None:
    """Export chunks to JSONL for eval dataset building."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            record = {
                "chunk_id": f"chunk_{i}",
                "text": chunk["text"],
                "section": chunk["section"],
                "subsection": chunk["subsection"],
                "header_path": chunk.get("header_path", ""),
                "word_count": len(chunk["text"].split()),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Indexer ───────────────────────────────────────────────────────────────


class Indexer(IndexerContract):
    """Indexes Cairn SRD markdown into ChromaDB with manual embeddings."""

    def __init__(
        self, config: RAGConfig | None = None, vector_store_path: str = "",
    ):
        if config:
            self._vector_store_path = config.vector_store_path
            self._model_name = config.embedding_model
        else:
            self._vector_store_path = vector_store_path
            self._model_name = "baai/bge-m3"

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

        import chromadb
        from party_of_one.embeddings import embed_texts

        documents = [c["text"] for c in raw_chunks]
        embeddings = embed_texts(
            documents, model=self._model_name,
        ).tolist()

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
        metadatas = [
            {"section": c["section"], "subsection": c["subsection"]}
            for c in raw_chunks
        ]

        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(
            "indexer_complete",
            chunks=len(raw_chunks),
            source=str(source_path),
        )
        return len(raw_chunks)
