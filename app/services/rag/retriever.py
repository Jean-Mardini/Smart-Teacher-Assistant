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

    chunk_text: str
    score: float
    document_id: str | None
    section_id: str | None
    section_heading: str
    page_start: int | None
    page_end: int | None
    chunk_id: str | None


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
                    chunk_text=str(r.get("chunk_text", "")),
                    score=score,
                    document_id=(
                        str(r["document_id"]) if r.get("document_id") is not None else None
                    ),
                    section_id=(
                        str(r["section_id"]) if r.get("section_id") is not None else None
                    ),
                    section_heading=str(r.get("section_heading", "")),
                    page_start=(
                        int(r["page_start"]) if r.get("page_start") is not None else None
                    ),
                    page_end=int(r["page_end"]) if r.get("page_end") is not None else None,
                    chunk_id=str(r["chunk_id"]) if r.get("chunk_id") is not None else None,
                )
            )

        return chunks


__all__ = ["Retriever", "RetrievedChunk"]

