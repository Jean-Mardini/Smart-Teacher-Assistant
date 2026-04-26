"""Simple JSON-backed vector store for local RAG."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

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

    def indexed_document_ids(self) -> set[str]:
        return {record["chunk"]["document_id"] for record in self._records}

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
        document_ids: List[str] | None = None,
    ) -> List[RetrievalResult]:
        query_embedding = embed_text(query)
        ranked: List[RetrievalResult] = []
        allowed_ids = set(document_ids or [])

        for record in self._records:
            if allowed_ids and record["chunk"]["document_id"] not in allowed_ids:
                continue
            score = cosine_similarity(query_embedding, record["embedding"])
            if score <= 0:
                continue

            ranked.append(
                RetrievalResult(
                    chunk=RAGChunk(**record["chunk"]),
                    score=score,
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]
