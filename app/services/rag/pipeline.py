from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from .chunker import chunk_text
from .embeddings import Embeddings
from .retriever import RetrievedChunk, Retriever
from .vector_store import VectorStore


MIN_RETRIEVAL_SCORE = 0.35


class RAGPipeline:
    """
    Retrieval-only RAG pipeline for integration with the external chat layer.

    Responsibilities:
      - Chunk section text.
      - Embed chunks and questions.
      - Store vectors and metadata in the vector store.
      - Retrieve relevant chunks for downstream generation.

    This module is intentionally retrieval-only. Final prompt assembly and LLM
    generation are handled externally by the chat/generation layer (Angela).
    """

    def __init__(
        self,
        embedding_model_name: str = "sentence-transformers/all-mpnet-base-v2",
        device: str = "cpu",
        vector_store: VectorStore | None = None,
        embeddings: Embeddings | None = None,
        retriever: Retriever | None = None,
    ) -> None:
        # CPU-friendly retrieval components.
        self.embeddings: Embeddings = embeddings or Embeddings(
            model_name=embedding_model_name,
            device=device,
        )
        self.vector_store: VectorStore = vector_store or VectorStore(
            dim=self.embeddings.dimension
        )
        self.retriever: Retriever = retriever or Retriever(self.vector_store)

    def _index_single_document(self, json_document: Dict[str, Any]) -> None:
        """
        Index one parsed document JSON into the vector store.

        Expected schema:
            {
              "document_id": "doc_001",
              "title": "...",
              "sections": [
                {
                  "section_id": "sec_1",
                  "heading": "...",
                  "page_start": 1,
                  "page_end": 2,
                  "text": "..."
                }
              ]
            }
        """
        document_id = str(json_document.get("document_id") or "")
        sections: Sequence[Dict[str, Any]] = json_document.get("sections", []) or []

        all_chunks: List[str] = []
        all_metadata: List[Dict[str, Any]] = []

        for section in sections:
            section_id = str(section.get("section_id") or "")
            heading = str(section.get("heading") or "")
            page_start = section.get("page_start")
            page_end = section.get("page_end")
            text = section.get("text") or ""

            if not isinstance(text, str) or not text.strip():
                continue

            chunks = chunk_text(text)
            for chunk_index, chunk in enumerate(chunks):
                chunk_id = f"{document_id}:{section_id}:{chunk_index}"
                all_chunks.append(chunk)
                all_metadata.append(
                    {
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "section_id": section_id,
                        "section_heading": heading,
                        "page_start": page_start,
                        "page_end": page_end,
                        "chunk_text": chunk,
                    }
                )

        if not all_chunks:
            return

        batch_embeddings = self.embeddings.embed_batch(all_chunks)
        self.vector_store.add_chunks(all_chunks, batch_embeddings, all_metadata)

    def index_documents(self, json_docs: Iterable[Dict[str, Any]]) -> None:
        """
        Index one or more structured JSON documents into the vector store.
        """
        for doc in json_docs:
            self._index_single_document(doc)

    def retrieve_chunks(self, question: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieval integration surface for the external chat/generation layer.

        Steps:
          1) Embed the incoming question.
          2) Retrieve relevant chunks from the vector store.
          3) Apply score threshold filtering.
          4) Return structured chunk payloads for external generation.

        Returns list schema:
            [
              {
                "chunk_id": "...",
                "document_id": "...",
                "section_id": "...",
                "section": "...",
                "page_start": 3,
                "page_end": 4,
                "score": 0.78,
                "text": "..."
              }
            ]
        """
        if not question.strip():
            return []

        query_embedding = self.embeddings.embed_text(question)
        retrieved_chunks: List[RetrievedChunk] = self.retriever.retrieve(
            query_embedding,
            top_k=top_k,
            min_score=MIN_RETRIEVAL_SCORE,
        )

        chunk_results: List[Dict[str, Any]] = []
        for chunk in retrieved_chunks:
            chunk_results.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "section_id": chunk.section_id,
                    "section": chunk.section_heading,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "score": chunk.score,
                    "text": chunk.chunk_text,
                }
            )

        return chunk_results


__all__ = ["RAGPipeline", "MIN_RETRIEVAL_SCORE"]


if __name__ == "__main__":
    import json

    sample_document = {
        "document_id": "doc_001",
        "title": "Introduction to Machine Learning",
        "sections": [
            {
                "section_id": "sec_1",
                "heading": "What is Machine Learning",
                "page_start": 1,
                "page_end": 2,
                "text": (
                    "Machine learning is a field of artificial intelligence that focuses on "
                    "algorithms that learn from data."
                ),
            },
            {
                "section_id": "sec_2",
                "heading": "Types of Machine Learning",
                "page_start": 3,
                "page_end": 4,
                "text": (
                    "There are three main types of machine learning: supervised learning, "
                    "unsupervised learning, and reinforcement learning."
                ),
            },
        ],
    }

    pipeline = RAGPipeline(device="cpu")
    pipeline.index_documents([sample_document])
    question = "What are the main types of machine learning?"
    result = pipeline.retrieve_chunks(question)

    print(json.dumps(result, indent=2, ensure_ascii=False))
