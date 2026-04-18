"""Data models for rubrics, grading results, and analytics outputs.

Kristy extends these as the evaluation layer is implemented.
"""

from pydantic import BaseModel, Field


class EvaluationStatusResponse(BaseModel):
    """Returned by GET /evaluation/status until all modules are wired."""

    rubrics_implemented: bool = False
    grading_implemented: bool = False
    feedback_implemented: bool = False
    analytics_implemented: bool = False
    note: str = Field(
        default="Implement app/services/evaluation/* and add POST routes here (Kristy)."
    )

