"""Routers for rubric generation, grading, and history (Kristy's Flexible Grader)."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from app.models.evaluation import (
    EvaluationStatusResponse,
    GradeSubmissionRequest,
    GradeSubmissionResponse,
    HistoryListResponse,
    RubricFromTextRequest,
    RubricGenerationResponse,
)
from app.services.evaluation import flexible_grader as fg

router = APIRouter()


@router.get("/status", response_model=EvaluationStatusResponse)
async def evaluation_status() -> EvaluationStatusResponse:
    return EvaluationStatusResponse()


@router.post("/rubric/from-assignment", response_model=RubricGenerationResponse)
async def rubric_from_assignment(body: RubricFromTextRequest) -> Dict[str, Any]:
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")
    try:
        result = fg.generate_items_from_assignment(text, body.total_points)
    except RuntimeError as e:
        if "GROQ_API_KEY" in str(e):
            raise HTTPException(
                status_code=503,
                detail="GROQ_API_KEY is not configured. Set it in the environment or data/evaluation/config.json.",
            ) from e
        raise HTTPException(status_code=500, detail=str(e)) from e
    return result


@router.post("/rubric/from-teacher-key", response_model=RubricGenerationResponse)
async def rubric_from_teacher_key(body: RubricFromTextRequest) -> Dict[str, Any]:
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")
    try:
        result = fg.generate_items_from_teacher_key(text, body.total_points)
    except RuntimeError as e:
        if "GROQ_API_KEY" in str(e):
            raise HTTPException(
                status_code=503,
                detail="GROQ_API_KEY is not configured. Set it in the environment or data/evaluation/config.json.",
            ) from e
        raise HTTPException(status_code=500, detail=str(e)) from e
    return result


@router.post("/grade", response_model=GradeSubmissionResponse)
async def grade_submission(body: GradeSubmissionRequest) -> GradeSubmissionResponse:
    submission = (body.submission_text or "").strip()
    if not submission:
        raise HTTPException(status_code=400, detail="submission_text is required.")
    if not body.items:
        raise HTTPException(status_code=400, detail="items must be a non-empty rubric.")
    try:
        result = fg.grade_submission_fast(
            submission_text=submission,
            items=body.items,
            teacher_key_text=body.teacher_key_text or "",
            reference_text=body.reference_text or "",
        )
    except RuntimeError as e:
        if "GROQ_API_KEY" in str(e):
            raise HTTPException(
                status_code=503,
                detail="GROQ_API_KEY is not configured.",
            ) from e
        raise HTTPException(status_code=500, detail=str(e)) from e

    record = fg.build_result_record(body.result_title, result, submission)
    return GradeSubmissionResponse(
        overall_score=float(result.get("overall_score", 0)),
        overall_out_of=int(result.get("overall_out_of", 0)),
        items_results=list(result.get("items_results", [])),
        record=record,
    )


@router.get("/history", response_model=HistoryListResponse)
async def evaluation_history(limit: int = Query(100, ge=1, le=500)) -> HistoryListResponse:
    return HistoryListResponse(records=fg.load_history(limit=limit))


@router.delete("/history")
async def clear_evaluation_history() -> Dict[str, str]:
    fg.clear_history()
    return {"status": "cleared"}

