"""Rubric generation and normalization (Kristy — Flexible Grader).

All logic is implemented in :mod:`app.services.evaluation.flexible_grader`. This module exposes
stable imports for “rubric” concerns without pulling the full grader surface area.
"""

from app.services.evaluation.flexible_grader import (
    generate_items_from_assignment,
    generate_items_from_teacher_key,
    get_active_rubric_items_for_grade,
    normalize_points,
    sanitize_assignment_item,
    sanitize_item_by_origin,
    sanitize_teacher_key_item,
    total_item_points,
)

__all__ = [
    "generate_items_from_assignment",
    "generate_items_from_teacher_key",
    "get_active_rubric_items_for_grade",
    "normalize_points",
    "sanitize_assignment_item",
    "sanitize_item_by_origin",
    "sanitize_teacher_key_item",
    "total_item_points",
]
