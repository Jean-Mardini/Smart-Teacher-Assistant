"""API models for LangGraph orchestration."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


IntentLiteral = Literal["auto", "dialogue", "summarize", "slides", "quiz", "grade"]


class GraphInvokeRequest(BaseModel):
    """Single entrypoint: LangGraph classifies (if auto) and runs the right teaching workflow."""

    message: str = ""
    intent: IntentLiteral = "auto"
    document_id: Optional[str] = None
    document_ids: list[str] = Field(default_factory=list)
    length: str = "medium"
    top_k: int = 3
    temperature: float = 0.2
    n_slides: int = 5
    n_questions: int = 5
    quiz_difficulty: str = "medium"
    submission_text: str = ""
    rubric_items: list[dict[str, Any]] = Field(default_factory=list)
    teacher_key_text: str = ""
    reference_text: str = ""
    result_title: str = "Submission"
    thread_id: str = "default"


class GraphSource(BaseModel):
    document_title: str
    section_heading: Optional[str] = None
    source_type: str = "section"
    page: Optional[str] = None


class GraphInvokeResponse(BaseModel):
    intent: str
    classify_reason: Optional[str] = None
    answer: str = ""
    sources: list[GraphSource] = Field(default_factory=list)
    processing_notes: list[str] = Field(default_factory=list)
    raw_result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class GraphInfoResponse(BaseModel):
    orchestration: str = "LangGraph"
    nodes: list[str]
    checkpointing: bool = True
