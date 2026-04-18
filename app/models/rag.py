"""Data models for RAG (chunks, retrieval results, queries, etc.)."""

"""angelas part"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class RAGChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    chunk_text: str
    chunk_index: int
    section_heading: Optional[str] = None
    source_path: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)


class RetrievalQuery(BaseModel):
    query: str
    top_k: int = 3


class ChunkingConfig(BaseModel):
    chunk_size: int = 900
    chunk_overlap: int = 150


class ReindexRequest(BaseModel):
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None

    @model_validator(mode="after")
    def validate_chunking(self):
        if self.chunk_size is not None and self.chunk_size < 50:
            raise ValueError("chunk_size must be at least 50.")
        if self.chunk_overlap is not None and self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be 0 or greater.")
        if (
            self.chunk_size is not None
            and self.chunk_overlap is not None
            and self.chunk_overlap >= self.chunk_size
        ):
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        return self


class RetrievalResult(BaseModel):
    chunk: RAGChunk
    score: float


class IndexingResult(BaseModel):
    indexed_documents: int
    indexed_chunks: int
    vector_store_path: str


class RAGStatus(BaseModel):
    knowledge_base_dir: str
    vector_store_path: str
    indexed_chunks: int
    indexed_documents: int
    available_documents: List[str] = Field(default_factory=list)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
