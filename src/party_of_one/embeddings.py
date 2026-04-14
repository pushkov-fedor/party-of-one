"""Embedding via OpenRouter API — replaces local sentence-transformers."""

from __future__ import annotations

import numpy as np

from party_of_one.agents.llm_client import create_openrouter_client
from party_of_one.logger import get_logger

logger = get_logger()

_BATCH_SIZE = 512


def embed_texts(
    texts: list[str],
    model: str = "baai/bge-m3",
) -> np.ndarray:
    """Compute L2-normalized embeddings via OpenRouter API.

    Returns ndarray of shape (len(texts), dim).
    """
    client = create_openrouter_client()
    all_embeddings: list[list[float]] = []

    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start : start + _BATCH_SIZE]
        response = client.embeddings.create(model=model, input=batch)
        sorted_data = sorted(response.data, key=lambda x: x.index)
        all_embeddings.extend(item.embedding for item in sorted_data)

    arr = np.array(all_embeddings, dtype=np.float32)

    # L2-normalize for cosine similarity via dot product
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    np.maximum(norms, 1e-12, out=norms)
    arr /= norms

    return arr
