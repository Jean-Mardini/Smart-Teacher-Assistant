"""Routers for chat-with-documents endpoints."""

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.services.agents.orchestration.assistant_graph import invoke_teaching_graph

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    length: str = "medium"
    top_k: int = 3
    temperature: float = 0.2
    document_ids: List[str] = Field(default_factory=list)
    thread_id: Optional[str] = Field(
        default=None,
        description="LangGraph checkpoint thread (conversation memory key).",
    )

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
    """Dialogue with documents — implemented via LangGraph (dialogue node → RAG + Groq)."""
    state = await invoke_teaching_graph(
        {
            "message": req.question,
            "intent": "dialogue",
            "document_ids": list(req.document_ids),
            "length": req.length,
            "top_k": req.top_k,
            "temperature": req.temperature,
        },
        thread_id=req.thread_id or "default",
    )
    sources_raw = state.get("sources") or []
    sources: List[ChatSource] = []
    for s in sources_raw:
        if isinstance(s, dict):
            sources.append(
                ChatSource(
                    document_title=s.get("document_title") or "Document",
                    section_heading=s.get("section_heading"),
                    source_type=s.get("source_type") or "section",
                    page=s.get("page"),
                )
            )
    notes = list(state.get("processing_notes") or [])
    err = state.get("error")
    if err:
        notes = [f"Error: {err}"] + notes
    return ChatResponse(
        answer=str(state.get("answer") or ""),
        sources=sources,
        processing_notes=notes,
    )
