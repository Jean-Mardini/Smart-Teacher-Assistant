"""Simple JSON-backed vector store for local RAG."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Set

from app.models.rag import RAGChunk, RetrievalResult
from app.services.knowledge.embeddings import cosine_similarity, embed_text
from app.storage.files import get_vector_store_path


class LocalVectorStore:
    def __init__(self, store_path: Path | None = None):
        self.store_path = store_path or get_vector_store_path()
        self._records = self._load()

    def _load(self) -> List[dict]:
        if not self.store_path.exists():
            return []

        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(self._records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        self._records = []
        self._save()

    def count(self) -> int:
        return len(self._records)

    def document_count(self) -> int:
        return len({record["chunk"]["document_id"] for record in self._records})

    def add_chunks(self, chunks: List[RAGChunk]) -> int:
        document_ids = {chunk.document_id for chunk in chunks}
        self._records = [
            record
            for record in self._records
            if record["chunk"]["document_id"] not in document_ids
        ]

        for chunk in chunks:
            self._records.append(
                {
                    "chunk": chunk.model_dump(),
                    "embedding": embed_text(chunk.chunk_text),
                }
            )

        self._save()
        return len(chunks)

    def similarity_search(
        self,
        query: str,
        top_k: int = 3,
        document_ids: Optional[List[str]] = None,
    ) -> List[RetrievalResult]:
        query_embedding = embed_text(query)
        ranked: List[RetrievalResult] = []
        allowed: Optional[Set[str]] = None
        if document_ids:
            allowed = {d.strip() for d in document_ids if d and str(d).strip()}

        for record in self._records:
            chunk_payload = record["chunk"]
            doc_id = chunk_payload.get("document_id")
            if allowed is not None and doc_id not in allowed:
                continue
            score = cosine_similarity(query_embedding, record["embedding"])
            if score <= 0:
                continue

            ranked.append(
                RetrievalResult(
                    chunk=RAGChunk(**chunk_payload),
                    score=score,
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)

        # Scoped chat: bag-of-token overlap can be zero for short/generic questions vs long chunks, or after
        # legacy empty embeddings; still return the beginning of the document so the LLM has context.
        if not ranked and allowed is not None and len(allowed) > 0:
            fallback: List[RetrievalResult] = []
            for record in self._records:
                chunk_payload = record["chunk"]
                if chunk_payload.get("document_id") not in allowed:
                    continue
                fallback.append(
                    RetrievalResult(
                        chunk=RAGChunk(**chunk_payload),
                        score=1e-6,
                    )
                )
            fallback.sort(key=lambda item: item.chunk.chunk_index)
            return fallback[:top_k]

        return ranked[:top_k]
