"""Retrieval logic for fetching relevant chunks from the vector store."""

from __future__ import annotations

from typing import List

from app.core.config import settings
from app.models.rag import RAGChunk
from app.services.knowledge.indexing_pipeline import index_knowledge_base
from app.services.knowledge.vector_store import LocalVectorStore


class Retriever:
    def __init__(self):
        self.store = LocalVectorStore()
        if self.store.count() == 0:
            index_knowledge_base(clear_first=True)
            self.store = LocalVectorStore()

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        document_ids: List[str] | None = None,
    ) -> List[RAGChunk]:
        top_k = top_k or settings.default_top_k
        results = self.store.similarity_search(
            query=query,
            top_k=top_k,
            document_ids=document_ids,
        )
        return [result.chunk for result in results]

    def refresh_index(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> dict:
        result = index_knowledge_base(
            clear_first=True,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.store = LocalVectorStore()
        return result.model_dump()
