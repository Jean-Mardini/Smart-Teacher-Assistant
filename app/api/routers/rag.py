"""Routers for RAG (indexing and retrieval) diagnostics and operations."""

from pathlib import Path

from fastapi import APIRouter

from app.models.rag import IndexingResult, RAGStatus, ReindexRequest
from app.services.knowledge.indexing_pipeline import list_local_document_infos_light
from app.services.knowledge.chunking_config import get_chunking_config
from app.services.knowledge.retrieval import Retriever
from app.services.knowledge.vector_store import LocalVectorStore
from app.storage.files import get_knowledge_base_dir, get_vector_store_path

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/status", response_model=RAGStatus)
async def rag_status():
    store = LocalVectorStore()
    docs = list_local_document_infos_light()
    return RAGStatus(
        knowledge_base_dir=str(get_knowledge_base_dir()),
        vector_store_path=str(get_vector_store_path()),
        indexed_chunks=store.count(),
        indexed_documents=store.document_count(),
        available_documents=[Path(d.path).name for d in docs],
        chunking=get_chunking_config(),
    )


@router.post("/reindex", response_model=IndexingResult)
async def reindex_knowledge_base(req: ReindexRequest | None = None):
    req = req or ReindexRequest()
    retriever = Retriever()
    result = retriever.refresh_index(
        chunk_size=req.chunk_size,
        chunk_overlap=req.chunk_overlap,
    )
    return IndexingResult(**result)
