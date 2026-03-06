from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from .chunker import chunk_text
from .embeddings import Embeddings
from .generator import AnswerGenerator, DEFAULT_LLM_MODEL
from .retriever import RetrievedChunk, Retriever
from .vector_store import VectorStore


class RAGPipeline:
    """
    Modular Retrieval-Augmented Generation pipeline.

    This class composes the following components:
      - `chunker.chunk_text` for text chunking.
      - `Embeddings` for turning text into dense vectors.
      - `VectorStore` for FAISS-based vector search.
      - `Retriever` for retrieving relevant chunks.
      - `AnswerGenerator` for LLM-based answer generation.

    The implementation is framework-agnostic and CPU-friendly, making it easy
    to integrate with FastAPI or other backends.
    """

    def __init__(
        self,
        embedding_model_name: str = "sentence-transformers/all-mpnet-base-v2",
        llm_model_name: str = DEFAULT_LLM_MODEL,
        device: str = "cpu",
        vector_store: VectorStore | None = None,
        embeddings: Embeddings | None = None,
        retriever: Retriever | None = None,
        generator: AnswerGenerator | None = None,
    ) -> None:
        # Embeddings
        self.embeddings: Embeddings = embeddings or Embeddings(
            model_name=embedding_model_name,
            device=device,
        )

        # Vector store
        self.vector_store: VectorStore = vector_store or VectorStore(
            dim=self.embeddings.dimension
        )

        # Retriever
        self.retriever: Retriever = retriever or Retriever(self.vector_store)

        # Generator (LLM)
        self.generator: AnswerGenerator = generator or AnswerGenerator(
            model_name=llm_model_name,
            device=device,
        )

    # ------------------------------------------------------------------ #
    # Indexing
    # ------------------------------------------------------------------ #
    def _index_single_document(self, json_document: Dict[str, Any]) -> None:
        """
        Index a single parsed document JSON into the vector store.

        Expected schema:
            {
              "document_id": "doc_001",
              "title": "...",
              "sections": [
                {
                  "section_id": "sec_1",
                  "heading": "What is Machine Learning",
                  "page_start": 1,
                  "page_end": 2,
                  "text": "..."
                },
                ...
              ]
            }
        """
        document_id = json_document.get("document_id")
        sections: Sequence[Dict[str, Any]] = json_document.get("sections", []) or []

        all_chunks: List[str] = []
        all_metadata: List[Dict[str, Any]] = []

        for section in sections:
            section_id = section.get("section_id")
            heading = section.get("heading") or ""
            page_start = section.get("page_start")
            page_end = section.get("page_end")
            text = section.get("text") or ""

            if not isinstance(text, str) or not text.strip():
                continue

            chunks = chunk_text(text)
            for chunk in chunks:
                all_chunks.append(chunk)
                all_metadata.append(
                    {
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

        embeddings = self.embeddings.embed_batch(all_chunks)
        self.vector_store.add_chunks(all_chunks, embeddings, all_metadata)

    def index_documents(self, json_docs: Iterable[Dict[str, Any]]) -> None:
        """
        Index one or more documents into the vector store.

        Args:
            json_docs: Iterable of document JSON objects following the schema
                described in `_index_single_document`.
        """
        for doc in json_docs:
            self._index_single_document(doc)

    # ------------------------------------------------------------------ #
    # Question answering
    # ------------------------------------------------------------------ #
    def answer_question(self, question: str, top_k: int = 3) -> Dict[str, Any]:
        """
        Answer a question using the indexed documents.

        Returns:
            JSON-serialisable dict with the schema:
                {
                  "answer": "...",
                  "sources": [
                    {
                      "section": "Types of Machine Learning",
                      "page": 3
                    }
                  ]
                }
        """
        if not question.strip():
            return {
                "answer": "Answer not found in the document.",
                "sources": [],
            }

        query_emb = self.embeddings.embed_text(question)
        retrieved_chunks: List[RetrievedChunk] = self.retriever.retrieve(
            query_emb,
            top_k=top_k,
            min_score=0.35,
        )

        if not retrieved_chunks:
            return {
                "answer": "Answer not found in the document.",
                "sources": [],
            }

        answer_text = self.generator.generate_answer(question, retrieved_chunks)

        # Deduplicate sources by (section_heading, page_start).
        seen: set[tuple[str, int]] = set()
        sources: List[Dict[str, Any]] = []
        for c in retrieved_chunks:
            key = (c.section_heading, c.page_start)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "section": c.section_heading,
                    "page": c.page_start,
                }
            )

        return {
            "answer": answer_text,
            "sources": sources,
        }


__all__ = ["RAGPipeline"]


if __name__ == "__main__":
    """
    Minimal end-to-end test for the RAG pipeline.

    This is intended for local verification only and will not execute
    when the module is imported elsewhere (e.g. in FastAPI routes).
    """

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
    result = pipeline.answer_question(question)

    print(json.dumps(result, indent=2, ensure_ascii=False))
