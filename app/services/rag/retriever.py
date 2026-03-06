from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from .vector_store import VectorStore


@dataclass
class RetrievedChunk:
    """
    Container for a retrieved chunk and its associated metadata.
    """

    score: float
    document_id: str
    section_id: str
    section_heading: str
    page_start: int
    page_end: int | None
    chunk_text: str


class Retriever:
    """
    Thin abstraction over the underlying `VectorStore`.
    """

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    def retrieve(
        self,
        query_embedding: np.ndarray,
        top_k: int = 3,
        min_score: float | None = None,
    ) -> List[RetrievedChunk]:
        """
        Retrieve the most relevant chunks for a given query embedding.

        Args:
            query_embedding: 1D or 2D NumPy array representing the query vector.
            top_k: Maximum number of chunks to retrieve.

        Returns:
            List of `RetrievedChunk` objects, sorted by similarity (best first).
        """
        raw_results = self._store.search(query_embedding, top_k=top_k)

        chunks: List[RetrievedChunk] = []
        for r in raw_results:
            score = float(r.get("score", 0.0))
            if min_score is not None and score < min_score:
                continue

            chunks.append(
                RetrievedChunk(
                    score=score,
                    document_id=str(r.get("document_id", "")),
                    section_id=str(r.get("section_id", "")),
                    section_heading=str(r.get("section_heading", "")),
                    page_start=int(r.get("page_start") or 0),
                    page_end=r.get("page_end"),
                    chunk_text=str(r.get("chunk_text", "")),
                )
            )

        return chunks


__all__ = ["Retriever", "RetrievedChunk"]

