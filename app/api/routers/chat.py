"""Routers for chat-with-documents endpoints."""

from importlib import import_module
from typing import Any, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.services.agents.chat_agent import run_chat

router = APIRouter()


def _init_retriever() -> Any:
    try:
        retrieval_module = import_module("app.services.knowledge.retrieval")
        retriever_cls = getattr(retrieval_module, "Retriever", None)

        if retriever_cls is None:
            print("Retriever init skipped: Retriever class is not available.")
            return None

        return retriever_cls()
    except Exception as e:
        print("Retriever init failed:", e)
        return None


retriever = _init_retriever()


class ChatRequest(BaseModel):
    question: str
    length: str = "medium"
    top_k: int = 3
    temperature: float = 0.2
    document_ids: List[str] = Field(default_factory=list)

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, value: int) -> int:
        return min(max(value, 1), 10)

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        return min(max(value, 0.0), 1.5)


class ChatSource(BaseModel):
    document_title: str
    section_heading: Optional[str] = None
    source_type: str = "section"
    page: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[ChatSource] = Field(default_factory=list)
    processing_notes: List[str] = Field(default_factory=list)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if retriever is None:
        return ChatResponse(
            answer="RAG not ready yet",
            sources=[],
            processing_notes=["Retriever not initialized"],
        )

    return await run_chat(
        question=req.question,
        retriever=retriever,
        length=req.length,
        top_k=req.top_k,
        temperature=req.temperature,
        document_ids=req.document_ids,
    )
