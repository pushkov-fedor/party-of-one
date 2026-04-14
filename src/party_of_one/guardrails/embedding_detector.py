"""Embedding-based injection detector — cosine similarity with known patterns."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from party_of_one.embeddings import embed_texts
from party_of_one.logger import get_logger

logger = get_logger()


class EmbeddingDetector:
    """Compares player input embedding against a bank of known injection patterns.

    Uses OpenRouter embeddings API (baai/bge-m3).
    """

    def __init__(
        self,
        patterns_path: str = "data/injection_patterns.yaml",
        model_name: str = "baai/bge-m3",
        threshold: float = 0.82,
    ):
        self._patterns_path = patterns_path
        self._model_name = model_name
        self.threshold = threshold
        self._pattern_embeddings = None
        self._patterns: list[str] = []
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy-load pattern embeddings via API."""
        if self._loaded:
            return
        self._loaded = True

        # Load patterns
        path = Path(self._patterns_path)
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f)
            self._patterns = data.get("patterns", [])
        else:
            logger.warning("injection_patterns_not_found", path=str(path))
            self._patterns = []

        # Pre-compute embeddings
        if self._patterns:
            self._pattern_embeddings = embed_texts(
                self._patterns, model=self._model_name,
            )
            logger.info("embedding_detector_ready",
                         patterns=len(self._patterns))
        else:
            self._pattern_embeddings = np.array([])

    def check(self, text: str) -> tuple[bool, str | None]:
        """Check if text is similar to any known injection pattern.

        Returns:
            (is_blocked, reason) — True + reason if blocked, False + None if safe.
        """
        self._ensure_loaded()

        if len(self._patterns) == 0:
            return False, None

        # Embed the input
        input_embedding = embed_texts([text], model=self._model_name)

        # Cosine similarity (embeddings already normalized → dot product)
        similarities = input_embedding @ self._pattern_embeddings.T
        max_idx = int(np.argmax(similarities))
        max_sim = float(similarities[0, max_idx])

        if max_sim >= self.threshold:
            matched_pattern = self._patterns[max_idx]
            reason = (
                f"embedding_similarity: {max_sim:.3f} "
                f"matched '{matched_pattern}'"
            )
            logger.warning("embedding_injection_detected",
                            similarity=max_sim, matched=matched_pattern,
                            input_preview=text[:100])
            return True, reason

        return False, None
