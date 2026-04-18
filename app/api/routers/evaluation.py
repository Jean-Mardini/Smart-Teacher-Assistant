"""Routers for rubric generation, grading, and analytics endpoints.

Kristy implements POST /rubric, /grade, etc. GET /status reports progress for the jury/UI.
"""

from fastapi import APIRouter

from app.models.evaluation import EvaluationStatusResponse

router = APIRouter()


@router.get("/status", response_model=EvaluationStatusResponse)
async def evaluation_status() -> EvaluationStatusResponse:
    """Shows which evaluation subsystems are implemented (flip flags as you ship)."""
    return EvaluationStatusResponse(
        rubrics_implemented=False,
        grading_implemented=False,
        feedback_implemented=False,
        analytics_implemented=False,
    )

