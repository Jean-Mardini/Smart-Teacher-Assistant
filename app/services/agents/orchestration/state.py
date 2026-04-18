"""Shared state for the LangGraph teaching assistant."""

from __future__ import annotations

from typing import Any, TypedDict


class TeachingAssistantState(TypedDict, total=False):
    """State passed between graph nodes (merged by LangGraph)."""

    # --- inputs (from API / user) ---
    message: str
    intent: str  # auto | dialogue | summarize | slides | quiz | grade
    document_id: str | None
    document_ids: list[str]
    length: str
    top_k: int
    temperature: float
    n_slides: int
    n_questions: int
    quiz_difficulty: str
    submission_text: str
    rubric_items: list[dict[str, Any]]
    teacher_key_text: str
    reference_text: str
    result_title: str

    # --- classifier ---
    classify_reason: str

    # --- outputs ---
    answer: str
    sources: list[dict[str, Any]]
    processing_notes: list[str]
    raw_result: dict[str, Any] | None
    error: str | None
