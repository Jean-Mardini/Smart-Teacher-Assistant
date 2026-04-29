from __future__ import annotations

from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer


class Embeddings:
    """
    Wrapper around a SentenceTransformer model used to create embeddings
    for both document chunks and user queries.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-mpnet-base-v2",
        device: str = "cpu",
    ) -> None:

        self.model = SentenceTransformer(model_name, device=device)
        self.dimension: int = self.model.get_sentence_embedding_dimension()

    def embed_text(self, text: str) -> np.ndarray:
        """
        Create embedding for a single text.
        """
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """
        Create embeddings for a batch of texts.
        """
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.astype(np.float32)