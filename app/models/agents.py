"""Data models describing inputs and outputs for all agents.

Each agent (summarizer, quiz, slides, rubric, grading, chat, cross-doc)
will have request/response models defined here.
"""

from typing import List, Literal, Optional

SlideTemplate = Literal[
    "academic_default",
    "minimal_clean",
    "workshop_interactive",
    "executive_summary",
    "deep_technical",
    "story_visual",
]

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------
# DOCUMENT STRUCTURE (Matheos format)
# ---------------------------

class Metadata(BaseModel):
    filename: str
    filetype: str
    total_pages: int


class Section(BaseModel):
    section_id: str
    heading: str
    level: int
    page_start: int
    page_end: int
    text: str


class Table(BaseModel):
    table_id: str
    page: int
    caption: Optional[str] = None
    text: str


class Image(BaseModel):
    image_id: str
    page: int
    caption: Optional[str] = None
    description: Optional[str] = None
    asset_path: Optional[str] = None


class DocumentIn(BaseModel):
    document_id: str
    title: str
    metadata: Metadata
    sections: List[Section] = Field(default_factory=list)
    tables: List[Table] = Field(default_factory=list)
    images: List[Image] = Field(default_factory=list)


# ---------------------------
# SUMMARY MODELS
# ---------------------------

SummaryLength = Literal["short", "medium", "long"]
SummaryExportFormat = Literal["docx", "pdf"]


class SummaryRequest(BaseModel):
    document_id: Optional[str] = None
    document_ids: List[str] = Field(default_factory=list)
    length: SummaryLength = "medium"

    @model_validator(mode="after")
    def validate_document_selection(self):
        if self.document_id and self.document_ids:
            raise ValueError("Provide either document_id or document_ids, not both.")
        if not self.document_id and not self.document_ids:
            raise ValueError("At least one document_id must be provided.")
        return self

    def resolved_document_ids(self) -> List[str]:
        return self.document_ids or [self.document_id]


class GlossaryItem(BaseModel):
    term: str = ""
    definition: str = ""


class SummaryResult(BaseModel):
    summary: str
    key_points: List[str]
    action_items: List[str] = Field(default_factory=list)
    formulas: List[str] = Field(default_factory=list)
    glossary: List[GlossaryItem] = Field(default_factory=list)
    source_documents: List[str] = Field(default_factory=list)
    total_pages: int = 0
    chunk_count: int = 0
    image_notes: List[str] = Field(default_factory=list)
    processing_notes: List[str] = Field(default_factory=list)


class SummaryExportRequest(BaseModel):
    """Client sends the last SummaryResult JSON plus desired file format."""

    format: SummaryExportFormat
    summary: str = ""
    key_points: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    formulas: List[str] = Field(default_factory=list)
    glossary: List[GlossaryItem] = Field(default_factory=list)
    source_documents: List[str] = Field(default_factory=list)
    total_pages: int = 0
    chunk_count: int = 0
    image_notes: List[str] = Field(default_factory=list)
    processing_notes: List[str] = Field(default_factory=list)


# ---------------------------
# SLIDE MODELS
# ---------------------------

ALL_SLIDE_LAYOUT_IDS: tuple[str, ...] = (
    "split_text_left",
    "split_text_right",
    "fullwidth_cards",
    "grid_quad",
    "grid_triple",
    "highlight_feature",
    "comparison",
    "process_flow",
    "image_dominant",
)

LEGACY_SLIDE_LAYOUT_MAP: dict[str, str] = {
    "classic_right": "split_text_left",
    "classic_left": "split_text_right",
    "two_column": "comparison",
    "panel_split": "highlight_feature",
}

SlideLayoutId = Literal[
    "split_text_left",
    "split_text_right",
    "fullwidth_cards",
    "grid_quad",
    "grid_triple",
    "highlight_feature",
    "comparison",
    "process_flow",
    "image_dominant",
    "classic_right",
    "classic_left",
    "two_column",
    "panel_split",
]


class Slide(BaseModel):
    slide_title: str
    """One-line context under the title (Gamma / deck style)."""
    subtitle: str = ""
    bullets: List[str]
    speaker_notes: Optional[str] = ""
    image_refs: List[str] = Field(default_factory=list)
    """On-slide composition for PPTX export (see ``slides.md``)."""
    image: Optional[str] = Field(
        default=None,
        description="Filesystem path to generated slide illustration when present (HF pipeline).",
    )
    layout: SlideLayoutId = "split_text_left"

    @field_validator("layout", mode="before")
    @classmethod
    def coerce_layout(cls, value: object) -> str:
        if not isinstance(value, str):
            return "split_text_left"
        v = value.strip()
        v = LEGACY_SLIDE_LAYOUT_MAP.get(v, v)
        if v in ALL_SLIDE_LAYOUT_IDS:
            return v
        return "split_text_left"


class SlideImageAsset(BaseModel):
    image_id: str
    page: int
    caption: Optional[str] = None
    description: Optional[str] = None
    asset_path: Optional[str] = None
    source: str = "document"
    prompt: Optional[str] = None


class SlideDeckResult(BaseModel):
    title: str
    slides: List[Slide]
    image_catalog: List[SlideImageAsset] = Field(default_factory=list)
    image_notes: List[str] = Field(default_factory=list)
    processing_notes: List[str] = Field(default_factory=list)
    """Echo of the slide template id used for generation (for PPTX export styling)."""
    template_used: Optional[str] = None


class SlideRequest(BaseModel):
    """Slides can be built from a **library document**, **pasted text**, a **one-line prompt**, or a **URL**."""

    document_id: Optional[str] = None
    """Indexed document id (Library). Used when ``source_text`` and ``source_url`` are empty."""

    source_text: Optional[str] = None
    """Raw notes, outline, or a one-line topic — becomes the sole source section for the LLM."""

    source_title: Optional[str] = None
    """Optional deck title when using ``source_text`` or ``source_url``."""

    source_url: Optional[str] = None
    """Fetch this http(s) page and extract text when set (no document_id required)."""

    n_slides: int = 5
    """Visual / rhetorical template passed into the slide LLM prompt."""
    template: SlideTemplate = "academic_default"
    """When True (default), one illustration per slide for PPTX (capped). Uses HF / xAI / OpenAI when configured; otherwise local placeholder PNGs if no image API keys (see slide_image_generator)."""
    generate_images: bool = True
    image_style: str = "vector_science"
    max_generated_images: int = Field(
        default=20,
        description="Max AI images to attempt; server clamps to min(n_slides, 20) when generate_images is True.",
    )

    @model_validator(mode="after")
    def validate_slide_request(self):
        has_doc = bool((self.document_id or "").strip())
        has_text = bool((self.source_text or "").strip())
        has_url = bool((self.source_url or "").strip())
        if not has_doc and not has_text and not has_url:
            raise ValueError("Provide document_id, source_text, or source_url.")
        if self.generate_images:
            self.max_generated_images = min(max(self.n_slides, 1), 20)
        else:
            self.max_generated_images = 0
        return self


# ---------------------------
# QUIZ MODELS
# ---------------------------

Difficulty = Literal["easy", "medium", "hard"]
QType = Literal["mcq", "short_answer"]


class QuizRequest(BaseModel):
    document_id: str
    difficulty: Difficulty = "medium"
    n_mcq: int = Field(default=3, ge=0, le=20, description="Multiple-choice questions (four options each).")
    n_short_answer: int = Field(
        default=2,
        ge=0,
        le=20,
        description="Short free-text / sentence-style questions.",
    )

    @model_validator(mode="after")
    def validate_quiz_counts(self) -> "QuizRequest":
        total = self.n_mcq + self.n_short_answer
        if total < 1:
            raise ValueError("n_mcq + n_short_answer must be at least 1.")
        if total > 25:
            raise ValueError("n_mcq + n_short_answer must be at most 25.")
        return self


class QuizQuestion(BaseModel):
    type: QType
    question: str
    options: List[str] = Field(default_factory=list)
    answer_index: Optional[int] = None
    answer_text: Optional[str] = None
    explanation: str
    difficulty: Difficulty
    source_refs: List[str]


class QuizResult(BaseModel):
    quiz: List[QuizQuestion]
