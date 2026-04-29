"""LangGraph orchestration API — routes teaching workflows through a single graph."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.graph import GraphInfoResponse, GraphInvokeRequest, GraphInvokeResponse, GraphSource
from app.services.agents.orchestration.assistant_graph import invoke_teaching_graph

router = APIRouter(prefix="/graph", tags=["langgraph"])


def _to_state(req: GraphInvokeRequest) -> dict:
    return {
        "message": req.message,
        "intent": req.intent,
        "document_id": req.document_id,
        "document_ids": list(req.document_ids),
        "length": req.length,
        "top_k": req.top_k,
        "temperature": req.temperature,
        "n_slides": req.n_slides,
        "n_questions": req.n_questions,
        "n_mcq": req.n_mcq,
        "n_short_answer": req.n_short_answer,
        "n_true_false": req.n_true_false,
        "quiz_difficulty": req.quiz_difficulty,
        "submission_text": req.submission_text,
        "rubric_items": list(req.rubric_items),
        "teacher_key_text": req.teacher_key_text,
        "reference_text": req.reference_text,
        "result_title": req.result_title,
    }


def _to_response(state: dict) -> GraphInvokeResponse:
    sources_raw = state.get("sources") or []
    sources: list[GraphSource] = []
    for s in sources_raw:
        if isinstance(s, dict):
            sources.append(
                GraphSource(
                    document_title=s.get("document_title") or "Document",
                    section_heading=s.get("section_heading"),
                    source_type=s.get("source_type") or "section",
                    page=s.get("page"),
                )
            )
    return GraphInvokeResponse(
        intent=str(state.get("intent") or "dialogue"),
        classify_reason=state.get("classify_reason"),
        answer=str(state.get("answer") or ""),
        sources=sources,
        processing_notes=list(state.get("processing_notes") or []),
        raw_result=state.get("raw_result") if isinstance(state.get("raw_result"), dict) else None,
        error=state.get("error"),
    )


@router.post("/invoke", response_model=GraphInvokeResponse)
async def graph_invoke(req: GraphInvokeRequest) -> GraphInvokeResponse:
    """Run the teaching assistant LangGraph (classify → dialogue | summarize | slides | quiz | grade)."""
    state = await invoke_teaching_graph(_to_state(req), thread_id=req.thread_id)
    return _to_response(dict(state))


@router.get("/info", response_model=GraphInfoResponse)
async def graph_info() -> GraphInfoResponse:
    return GraphInfoResponse(
        nodes=[
            "classify_intent",
            "dialogue",
            "summarize",
            "slides",
            "quiz",
            "grade",
        ],
    )
