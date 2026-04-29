"""Data models for rubrics, grading results, and analytics outputs.

API request/response shapes for Kristy's Flexible Grader live here; service logic is in
``app/services/evaluation/flexible_grader.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

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


class EvaluationConfigResponse(BaseModel):
    """Public evaluation config summary for the frontend."""

    has_api_key: bool = False
    api_key_preview: str = ""
    model: str = ""


class EvaluationConfigUpdateRequest(BaseModel):
    """Save or clear Groq-backed evaluation settings."""

    groq_api_key: Optional[str] = None
    model: Optional[str] = None


class SourceTextRequest(BaseModel):
    text: str = ""
    document_ids: List[str] = Field(default_factory=list)


class SourceTextResponse(BaseModel):
    text: str = ""
    documents: List[Dict[str, str]] = Field(default_factory=list)


class RubricFromTextRequest(BaseModel):
    """Generate rubric items from assignment or teacher-key text."""

    text: str = Field("", description="Assignment text or teacher key text.")
    document_ids: List[str] = Field(default_factory=list)
    total_points: int = Field(100, ge=1, le=2000)
    default_grounding: Optional[Literal["ai", "reference", "hybrid"]] = Field(
        default=None,
        description="For QA / teacher-key rubrics: force this grounding on every conceptual item.",
    )


class MoodleXmlPayload(BaseModel):
    """Parse a Moodle ``<quiz>`` XML answer key into rubric-style items (exact mode)."""

    xml: str = Field("", description="Moodle <quiz> XML string.")


class GradeMoodleMcqRequest(BaseModel):
    """Deterministic MCQ grading: two Moodle XML documents with matching question names."""

    key_xml: str = ""
    student_xml: str = ""
    result_title: str = "Moodle MCQ"
    save_history: bool = True


class MoodleMcqStudentSubmission(BaseModel):
    """One learner Moodle ``<quiz>`` XML in an MCQ batch."""

    title: str = "Submission"
    student_xml: str = ""


class GradeMoodleMcqBatchRequest(BaseModel):
    """One answer key; multiple student Moodle XML attempts (same shape as text batch results)."""

    key_xml: str = ""
    submissions: List[MoodleMcqStudentSubmission] = Field(default_factory=list)
    batch_name: str = ""
    save_history: bool = True


class RubricGenerationResponse(BaseModel):
    """LLM rubric payload (items are normalized to total_points)."""

    rubric_title: Optional[str] = None
    summary: List[Any] = Field(default_factory=list)
    items: List[Dict[str, Any]] = Field(default_factory=list)


class GradeSubmissionRequest(BaseModel):
    """Grade one submission against rubric items."""

    submission_text: str = ""
    submission_document_ids: List[str] = Field(default_factory=list)
    items: List[Dict[str, Any]]
    teacher_key_text: str = ""
    teacher_key_document_ids: List[str] = Field(default_factory=list)
    reference_text: str = ""
    reference_document_ids: List[str] = Field(default_factory=list)
    result_title: str = "Submission"
    save_history: bool = True


class GradeSubmissionResponse(BaseModel):
    overall_score: float
    overall_out_of: int
    items_results: List[Dict[str, Any]]
    record: Optional[Dict[str, Any]] = None


class HistoryListResponse(BaseModel):
    records: List[Dict[str, Any]]
    batches: List[Dict[str, Any]] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(default_factory=dict)


class BatchSubmissionInput(BaseModel):
    title: str = "Submission"
    submission_text: str = ""
    submission_document_ids: List[str] = Field(default_factory=list)


class BatchGradeRequest(BaseModel):
    submissions: List[BatchSubmissionInput] = Field(default_factory=list)
    items: List[Dict[str, Any]] = Field(default_factory=list)
    teacher_key_text: str = ""
    teacher_key_document_ids: List[str] = Field(default_factory=list)
    reference_text: str = ""
    reference_document_ids: List[str] = Field(default_factory=list)
    batch_name: str = ""
    save_history: bool = True


class BatchGradeResponse(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list)
    batch_id: str = ""
    batch_name: str = ""
    stats: Dict[str, Any] = Field(default_factory=dict)


class EvaluationPresetSaveRequest(BaseModel):
    origin: str = "assignment"
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total_points: int = Field(100, ge=1, le=2000)


class EvaluationPresetsResponse(BaseModel):
    presets: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class ParsedUploadText(BaseModel):
    name: str
    text: str


class ParsedUploadListResponse(BaseModel):
    items: List[ParsedUploadText] = Field(default_factory=list)


class ExportSingleRequest(BaseModel):
    record: Dict[str, Any]


class ExportBatchRequest(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list)


class HistoryRecordUpdateRequest(BaseModel):
    record: Dict[str, Any]
