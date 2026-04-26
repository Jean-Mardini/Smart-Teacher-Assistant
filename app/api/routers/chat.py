"""Routers for chat-with-documents endpoints."""

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.services.agents.orchestration.assistant_graph import invoke_teaching_graph
from app.services.knowledge.indexing_pipeline import list_local_document_infos_light

router = APIRouter()


def _resolve_document_ids(raw_ids: list[str]) -> list[str]:
    """Map partial or typo ids to real library ids when there is exactly one prefix match."""
    cleaned = [x.strip() for x in raw_ids if x and str(x).strip()]
    if not cleaned:
        return []
    try:
        catalog = list_local_document_infos_light()
    except Exception:
        return cleaned
    known = {d.document_id for d in catalog}
    out: list[str] = []
    for r in cleaned:
        if r in known:
            out.append(r)
            continue
        hits = [d.document_id for d in catalog if d.document_id.startswith(r)]
        if len(hits) == 1:
            out.append(hits[0])
        else:
            out.append(r)
    return list(dict.fromkeys(out))


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
    doc_ids = _resolve_document_ids(list(req.document_ids))
    state = await invoke_teaching_graph(
        {
            "message": req.question,
            "intent": "dialogue",
            "document_ids": doc_ids,
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
