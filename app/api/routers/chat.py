"""Routers for chat-with-documents endpoints."""

from importlib import import_module
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

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


class ChatResponse(BaseModel):
    answer: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if retriever is None:
        return {"answer": "RAG not ready yet"}

    return await run_chat(
        question=req.question,
        retriever=retriever,
    )
