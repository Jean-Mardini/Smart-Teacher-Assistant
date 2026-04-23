"""LangGraph orchestration: routes teaching tasks to RAG chat, agents, and evaluation."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.services.agents.chat_agent import run_chat
from app.services.agents.quiz_agent import run_quiz
from app.services.agents.slide_agent import run_slides
from app.services.agents.summarizer_agent import run_summarizer
from app.services.evaluation import flexible_grader as fg
from app.services.knowledge.indexing_pipeline import get_local_document_by_id
from app.services.knowledge.retrieval import Retriever
from app.services.llm.groq_client import call_llm_json
from app.services.agents.orchestration.state import TeachingAssistantState

logger = logging.getLogger(__name__)

_VALID_INTENTS = frozenset({"dialogue", "summarize", "slides", "quiz", "grade"})

_retriever: Retriever | None = None
_compiled_graph: Any = None


def invalidate_retriever_cache() -> None:
    """Call after reindex/upload so the next dialogue uses a fresh vector store (not a stale in-memory snapshot)."""
    global _retriever
    _retriever = None


def _get_retriever() -> Retriever | None:
    global _retriever
    if _retriever is None:
        try:
            _retriever = Retriever()
        except Exception as e:
            logger.warning("Retriever init failed: %s", e)
            return None
    return _retriever


async def node_classify_intent(state: TeachingAssistantState) -> dict[str, Any]:
    intent = (state.get("intent") or "auto").strip().lower()
    if intent != "auto":
        if intent not in _VALID_INTENTS:
            intent = "dialogue"
        return {"intent": intent, "classify_reason": "fixed by request"}

    message = (state.get("message") or "").strip()
    if not message:
        return {"intent": "dialogue", "classify_reason": "empty message"}

    try:
        system = (
            "You route teacher assistant requests. Reply with JSON only, no markdown:\n"
            '{"intent":"dialogue"|"summarize"|"slides"|"quiz"|"grade","reason":"one short sentence"}\n'
            "- dialogue: questions, explanations, tutoring about materials\n"
            "- summarize: wants a summary or overview of document(s)\n"
            "- slides: wants slide deck / presentation from a document\n"
            "- quiz: wants quiz or exam questions\n"
            "- grade: wants grading, scores, rubric application, feedback on student work"
        )
        raw = call_llm_json(system=system, user=f"Teacher request:\n{message}", temperature=0.0)
        guessed = str(raw.get("intent", "dialogue")).lower().strip()
        reason = str(raw.get("reason", ""))
        if guessed not in _VALID_INTENTS:
            guessed = "dialogue"
        return {"intent": guessed, "classify_reason": reason}
    except Exception as e:
        logger.warning("Intent classification failed: %s", e)
        return {"intent": "dialogue", "classify_reason": f"classify error: {e}"}


def _route_after_classify(state: TeachingAssistantState) -> Literal["dialogue", "summarize", "slides", "quiz", "grade"]:
    i = (state.get("intent") or "dialogue").lower().strip()
    if i not in _VALID_INTENTS:
        return "dialogue"
    return i  # type: ignore[return-value]


async def node_dialogue(state: TeachingAssistantState) -> dict[str, Any]:
    retriever = _get_retriever()
    if retriever is None:
        return {
            "answer": "RAG is not ready. Upload documents, run reindex, and try again.",
            "sources": [],
            "processing_notes": ["Retriever could not be initialized."],
            "raw_result": None,
            "error": None,
        }

    out = await run_chat(
        question=state.get("message") or "",
        retriever=retriever,
        length=state.get("length") or "medium",
        top_k=int(state.get("top_k") or 3),
        temperature=float(state.get("temperature") or 0.2),
        document_ids=state.get("document_ids") or None,
    )
    return {
        "answer": out.get("answer", ""),
        "sources": out.get("sources") or [],
        "processing_notes": out.get("processing_notes") or [],
        "raw_result": None,
        "error": None,
    }


async def node_summarize(state: TeachingAssistantState) -> dict[str, Any]:
    ids = list(state.get("document_ids") or [])
    if state.get("document_id"):
        ids = [state["document_id"]] + [x for x in ids if x != state["document_id"]]
    ids = [x for x in ids if x][:10]
    if not ids:
        return {
            "answer": "",
            "sources": [],
            "processing_notes": [],
            "raw_result": None,
            "error": "Provide document_id or document_ids to summarize.",
        }

    docs: list[dict[str, Any]] = []
    for did in ids:
        doc = get_local_document_by_id(did)
        if doc is not None:
            docs.append(doc.model_dump())

    if not docs:
        return {
            "answer": "",
            "sources": [],
            "processing_notes": [],
            "raw_result": None,
            "error": "No matching documents in the library.",
        }

    result = await run_summarizer(docs, length=state.get("length") or "medium")
    data = result.model_dump()
    return {
        "answer": data.get("summary", "") or "",
        "sources": [],
        "processing_notes": data.get("processing_notes") or [],
        "raw_result": data,
        "error": None,
    }


def _load_document_dict(document_id: str) -> dict[str, Any] | None:
    doc = get_local_document_by_id(document_id)
    return doc.model_dump() if doc is not None else None


async def node_slides(state: TeachingAssistantState) -> dict[str, Any]:
    did = (state.get("document_id") or "").strip() or (state.get("document_ids") or [None])[0]
    if not did:
        return {
            "answer": "",
            "sources": [],
            "processing_notes": [],
            "raw_result": None,
            "error": "Provide document_id for slide generation.",
        }
    doc = _load_document_dict(did)
    if doc is None:
        return {
            "answer": "",
            "sources": [],
            "processing_notes": [],
            "raw_result": None,
            "error": f"Document '{did}' not found.",
        }

    try:
        result = await run_slides(
            doc,
            n_slides=int(state.get("n_slides") or 5),
            template="academic_default",
            generate_images=True,
            max_generated_images=min(max(int(state.get("n_slides") or 5), 1), 20),
        )
    except RuntimeError as exc:
        return {
            "answer": "",
            "sources": [],
            "processing_notes": [],
            "raw_result": None,
            "error": str(exc),
        }
    data = result.model_dump()
    title = data.get("title") or "Slides"
    return {
        "answer": f"Generated slide deck: {title} ({len(data.get('slides') or [])} slides).",
        "sources": [],
        "processing_notes": data.get("processing_notes") or [],
        "raw_result": data,
        "error": None,
    }


async def node_quiz(state: TeachingAssistantState) -> dict[str, Any]:
    did = (state.get("document_id") or "").strip() or (state.get("document_ids") or [None])[0]
    if not did:
        return {
            "answer": "",
            "sources": [],
            "processing_notes": [],
            "raw_result": None,
            "error": "Provide document_id for quiz generation.",
        }
    doc = _load_document_dict(did)
    if doc is None:
        return {
            "answer": "",
            "sources": [],
            "processing_notes": [],
            "raw_result": None,
            "error": f"Document '{did}' not found.",
        }

    n_mcq_raw = state.get("n_mcq")
    n_short_raw = state.get("n_short_answer")
    if n_mcq_raw is not None or n_short_raw is not None:
        n_mcq = max(0, min(20, int(n_mcq_raw or 0)))
        n_short = max(0, min(20, int(n_short_raw or 0)))
    else:
        total = max(1, min(25, int(state.get("n_questions") or 5)))
        n_mcq = min(total, (total * 3 + 2) // 5)
        n_short = total - n_mcq
    if n_mcq + n_short < 1:
        n_mcq, n_short = 3, 2

    result = await run_quiz(
        doc,
        n_mcq=n_mcq,
        n_short_answer=n_short,
        difficulty=str(state.get("quiz_difficulty") or "medium"),
    )
    data = result.model_dump()
    n = len(data.get("quiz") or [])
    return {
        "answer": f"Generated quiz with {n} questions.",
        "sources": [],
        "processing_notes": [],
        "raw_result": data,
        "error": None,
    }


async def node_grade(state: TeachingAssistantState) -> dict[str, Any]:
    submission = (state.get("submission_text") or "").strip()
    items = state.get("rubric_items") or []
    if not submission:
        return {
            "answer": "",
            "sources": [],
            "processing_notes": [],
            "raw_result": None,
            "error": "Provide submission_text for grading.",
        }
    if not items:
        return {
            "answer": "",
            "sources": [],
            "processing_notes": [],
            "raw_result": None,
            "error": "Provide rubric_items (list of rubric dicts) for grading.",
        }

    try:
        result = fg.grade_submission_fast(
            submission_text=submission,
            items=items,
            teacher_key_text=state.get("teacher_key_text") or "",
            reference_text=state.get("reference_text") or "",
        )
        record = fg.build_result_record(
            state.get("result_title") or "Graded submission",
            result,
            submission,
        )
        payload = {"grade": result, "record": record}
        score = result.get("overall_score", 0)
        out_of = result.get("overall_out_of", 0)
        return {
            "answer": f"Graded: {score} / {out_of}",
            "sources": [],
            "processing_notes": ["Grading complete. Inspect raw_result for full rationale and item scores."],
            "raw_result": payload,
            "error": None,
        }
    except Exception as e:
        logger.exception("Grading failed")
        return {
            "answer": "",
            "sources": [],
            "processing_notes": [],
            "raw_result": None,
            "error": str(e),
        }


def build_teaching_graph() -> StateGraph:
    builder = StateGraph(TeachingAssistantState)
    builder.add_node("classify_intent", node_classify_intent)
    builder.add_node("dialogue", node_dialogue)
    builder.add_node("summarize", node_summarize)
    builder.add_node("slides", node_slides)
    builder.add_node("quiz", node_quiz)
    builder.add_node("grade", node_grade)

    builder.add_edge(START, "classify_intent")
    builder.add_conditional_edges(
        "classify_intent",
        _route_after_classify,
        {
            "dialogue": "dialogue",
            "summarize": "summarize",
            "slides": "slides",
            "quiz": "quiz",
            "grade": "grade",
        },
    )
    for n in ("dialogue", "summarize", "slides", "quiz", "grade"):
        builder.add_edge(n, END)
    return builder


def get_compiled_graph():
    """Compiled graph with in-memory checkpointing (per-thread conversation state)."""
    global _compiled_graph
    if _compiled_graph is None:
        checkpointer = MemorySaver()
        _compiled_graph = build_teaching_graph().compile(checkpointer=checkpointer)
    return _compiled_graph


async def invoke_teaching_graph(
    state: dict[str, Any],
    thread_id: str = "default",
) -> TeachingAssistantState:
    """Run the teaching assistant graph."""
    graph = get_compiled_graph()
    cfg = {"configurable": {"thread_id": thread_id}}
    result = await graph.ainvoke(state, cfg)
    return result  # type: ignore[return-value]
