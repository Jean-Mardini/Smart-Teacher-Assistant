"""Routers for chat-with-documents endpoints.

Currently empty – Mark, Angela, and Jean will add endpoints later.
"""

from fastapi import APIRouter
from pydantic import BaseModel

# ----------- AGENT -----------
from app.services.agents.chat_agent import run_chat

# ----------- RAG (MARK) -----------
from app.services.knowledge.retrieval import Retriever

router = APIRouter()


# ---------------------------
# INIT RETRIEVER
# ---------------------------
retriever = None
try:
    retriever = Retriever()
except Exception as e:
    print("Retriever init failed:", e)


# ---------------------------
# MODELS
# ---------------------------
class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str


# ---------------------------
# CHAT ENDPOINT
# ---------------------------
@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):

    if retriever is None:
        return {"answer": "RAG not ready yet"}

    result = await run_chat(
        question=req.question,
        retriever=retriever
    )

    return result
