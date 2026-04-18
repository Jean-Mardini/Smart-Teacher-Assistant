"""Grading: apply rubrics to submissions (Kristy — Flexible Grader).

Implementation: :func:`grade_submission_fast` and helpers in
:mod:`app.services.evaluation.flexible_grader`.
"""

from app.services.evaluation.flexible_grader import (
    build_result_record,
    grade_submission_fast,
    prepare_items_with_reference_context,
)

__all__ = [
    "build_result_record",
    "grade_submission_fast",
    "prepare_items_with_reference_context",
]
