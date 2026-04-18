from __future__ import annotations

from typing import Dict, List, Optional

import faiss
import numpy as np


class VectorStore:
    """
    Simple in-memory FAISS vector store for RAG.

    Uses cosine similarity implemented via an inner-product index on
    L2-normalised embeddings.

    The FAISS index stores the dense vectors, while a parallel in-memory
    dictionary stores metadata keyed by vector id.
    """

    def __init__(self, dim: int, use_gpu: bool = False) -> None:
        """
        Args:
            dim: Dimensionality of the embeddings.
            use_gpu: Reserved for future use. Currently, only CPU is used
                to keep the system lightweight and laptop-friendly.
        """
        if dim <= 0:
            raise ValueError("Vector dimension must be a positive integer.")

        self.dim = dim
        # Cosine similarity via inner product on normalised vectors.
        self.index = faiss.IndexFlatIP(dim)
        self._next_id: int = 0
        self._metadata: Dict[int, Dict] = {}
        self._use_gpu = use_gpu  # Not used now, but kept for extensibility.

    @staticmethod
    def _ensure_2d(embeddings: np.ndarray) -> np.ndarray:
        if embeddings.ndim == 1:
            return embeddings.reshape(1, -1)
        return embeddings

    @staticmethod
    def _l2_normalise(embeddings: np.ndarray) -> np.ndarray:
        """
        L2-normalise embeddings along the last axis for cosine similarity.
        """
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-12
        return embeddings / norms

    def add_chunks(
        self,
        chunks: List[str],
        embeddings: np.ndarray,
        metadata: List[Dict],
    ) -> None:
        """
        Add chunks and their embeddings to the FAISS index.

        Args:
            chunks: List of chunk texts; primarily for length validation.
            embeddings: 2D NumPy array of shape (n_chunks, dim).
            metadata: List of metadata dicts, one per chunk. Each dict should
                include at least:
                    - chunk_id (optional but recommended)
                    - document_id
                    - section_id
                    - section_heading
                    - page_start
                    - page_end (optional)
                    - chunk_text
        """
        if len(chunks) == 0:
            return

        if len(chunks) != len(metadata):
            raise ValueError("Number of chunks and metadata items must match.")

        embeddings = np.asarray(embeddings, dtype=np.float32)
        embeddings = self._ensure_2d(embeddings)

        if embeddings.shape[1] != self.dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.dim}, got {embeddings.shape[1]}"
            )

        if embeddings.shape[0] != len(chunks):
            raise ValueError(
                "Number of embeddings does not match number of chunks."
            )

        # Normalise for cosine similarity.
        embeddings = self._l2_normalise(embeddings)

        # Add to FAISS.
        self.index.add(embeddings)

        # Store metadata keyed by the global vector ids assigned by this store.
        for i, meta in enumerate(metadata):
            vector_id = self._next_id + i
            # Ensure chunk_text is present in metadata for downstream use.
            if "chunk_text" not in meta:
                meta = {**meta, "chunk_text": chunks[i]}
            self._metadata[vector_id] = meta

        self._next_id += len(chunks)

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 3,
    ) -> List[Dict]:
        """
        Search the index for the most similar chunks to a query embedding.

        Args:
            query_embedding: 1D or 2D NumPy array representing the query.
            top_k: Maximum number of results to return.

        Returns:
            List of result dicts, each containing:
                - score: similarity score (float)
                - all keys from the stored metadata for the chunk
        """
        if self.index.ntotal == 0:
            return []

        if top_k <= 0:
            return []

        q = np.asarray(query_embedding, dtype=np.float32)
        q = self._ensure_2d(q)
        q = self._l2_normalise(q)

        scores, indices = self.index.search(q, top_k)
        scores = scores[0]
        indices = indices[0]

        results: List[Dict] = []
        for score, idx in zip(scores, indices):
            if idx < 0:
                continue
            meta: Optional[Dict] = self._metadata.get(int(idx))
            if meta is None:
                continue
            result = {"score": float(score), **meta}
            results.append(result)

        return results


__all__ = ["VectorStore"]

