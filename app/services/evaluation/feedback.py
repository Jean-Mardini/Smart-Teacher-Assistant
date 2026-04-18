"""Feedback tied to grading results (Kristy — Flexible Grader).

Per-item **rationale**, **suggestions**, and **evidence** are produced inside
:func:`~app.services.evaluation.flexible_grader.grade_submission_fast` and returned in
``items_results`` on the grading payload. There is no separate LLM pass here; export helpers
(:func:`~app.services.evaluation.flexible_grader.export_single_report`, HTML/DOCX builders)
format the same structured output for teachers.

For programmatic access, use :mod:`grading` or import from ``flexible_grader`` directly.
"""

from app.services.evaluation.flexible_grader import (
    build_batch_docx_report,
    build_batch_report_html,
    build_docx_report,
    build_single_report_html,
    export_batch_report,
    export_single_report,
)

__all__ = [
    "export_single_report",
    "export_batch_report",
    "build_docx_report",
    "build_batch_docx_report",
    "build_single_report_html",
    "build_batch_report_html",
]
