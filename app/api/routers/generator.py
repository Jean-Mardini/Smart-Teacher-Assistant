"""Routers for assignment/exam generation and lesson-plan generation."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.generator import (
    AssignmentGenRequest,
    AssignmentGenResponse,
    ExamGenRequest,
    ExamGenResponse,
    LessonPlanRequest,
    LessonPlanResponse,
)
from app.services.evaluation import generator as gen
from app.services.evaluation.flexible_grader import compose_text_from_sources

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generator", tags=["generator"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _resolve_text(text: str, document_ids: List[str]) -> str:
    resolved = compose_text_from_sources(manual_text=text or "", document_ids=document_ids or [])
    return str(resolved.get("text", "")).strip()


# ---------------------------------------------------------------------------
# Assignment generator (streaming SSE)
# ---------------------------------------------------------------------------

async def _stream_assignment(body: AssignmentGenRequest) -> AsyncGenerator[str, None]:
    try:
        yield _sse({"status": "resolving", "message": "Resolving source material…"})
        text = await asyncio.to_thread(_resolve_text, body.text, body.document_ids)
        if not text:
            yield _sse({"error": "Provide source text or select at least one library document."})
            return
        yield _sse({"status": "generating", "message": f"Generating {body.difficulty} assignment ({body.task_count} tasks, {body.total_points} pts)…"})
        result = await asyncio.to_thread(
            gen.generate_assignment,
            source_text=text,
            difficulty=body.difficulty,
            total_points=body.total_points,
            task_count=body.task_count,
        )
        yield _sse({"done": True, **result})
    except Exception as exc:
        logger.warning("Assignment generation failed", exc_info=True)
        yield _sse({"error": str(exc)})


@router.post("/assignment/stream")
async def generate_assignment_stream(body: AssignmentGenRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_assignment(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Exam generator (streaming SSE)
# ---------------------------------------------------------------------------

async def _stream_exam(body: ExamGenRequest) -> AsyncGenerator[str, None]:
    try:
        yield _sse({"status": "resolving", "message": "Resolving source material…"})
        text = await asyncio.to_thread(_resolve_text, body.text, body.document_ids)
        if not text:
            yield _sse({"error": "Provide source text or select at least one library document."})
            return
        types_label = ", ".join(body.question_types) if body.question_types else "mixed"
        yield _sse({"status": "generating", "message": f"Generating {body.difficulty} exam ({body.question_count} questions, {types_label}, {body.total_points} pts)…"})
        result = await asyncio.to_thread(
            gen.generate_exam,
            source_text=text,
            difficulty=body.difficulty,
            total_points=body.total_points,
            question_types=body.question_types,
            question_count=body.question_count,
        )
        yield _sse({"done": True, **result})
    except Exception as exc:
        logger.warning("Exam generation failed", exc_info=True)
        yield _sse({"error": str(exc)})


@router.post("/exam/stream")
async def generate_exam_stream(body: ExamGenRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_exam(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Lesson plan generator
# ---------------------------------------------------------------------------

@router.post("/lesson-plan", response_model=LessonPlanResponse)
async def generate_lesson_plan(body: LessonPlanRequest) -> Dict[str, Any]:
    if not body.weak_criteria:
        return {}
    result = await asyncio.to_thread(
        gen.generate_lesson_plan,
        weak_criteria=body.weak_criteria,
        class_average_pct=body.class_average_pct,
        context=body.context,
    )
    return result
