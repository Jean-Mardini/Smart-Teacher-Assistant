"""Data models for rubrics, grading results, and analytics outputs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvaluationStatusResponse(BaseModel):
    """Returned by GET /evaluation/status."""

    rubrics_implemented: bool = True
    grading_implemented: bool = True
    feedback_implemented: bool = True
    analytics_implemented: bool = False
    note: str = Field(
        default="Flexible Grader (Kristy): Groq + rubrics + grading + exports. See POST /evaluation/*."
    )


class RubricFromTextRequest(BaseModel):
    """Generate rubric items from assignment or teacher-key text."""

    text: str = Field(..., description="Assignment text or teacher key text.")
    total_points: int = Field(100, ge=1, le=2000)


class RubricGenerationResponse(BaseModel):
    """LLM rubric payload (items are normalized to total_points)."""

    rubric_title: Optional[str] = None
    summary: List[Any] = Field(default_factory=list)
    items: List[Dict[str, Any]] = Field(default_factory=list)


class GradeSubmissionRequest(BaseModel):
    """Grade one submission against rubric items."""

    submission_text: str
    items: List[Dict[str, Any]]
    teacher_key_text: str = ""
    reference_text: str = ""
    result_title: str = "Submission"


class GradeSubmissionResponse(BaseModel):
    overall_score: float
    overall_out_of: int
    items_results: List[Dict[str, Any]]
    record: Optional[Dict[str, Any]] = None


class HistoryListResponse(BaseModel):
    records: List[Dict[str, Any]]
