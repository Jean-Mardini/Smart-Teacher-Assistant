"""Data models describing inputs and outputs for all agents.

Each agent (summarizer, quiz, slides, rubric, grading, chat, cross-doc)
will have request/response models defined here.
"""

"""angelas part"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


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
    term: str
    definition: str


class SummaryResult(BaseModel):
    summary: str
    key_points: List[str]
    action_items: List[str] = Field(default_factory=list)
    glossary: List[GlossaryItem] = Field(default_factory=list)
    source_documents: List[str] = Field(default_factory=list)
    total_pages: int = 0
    chunk_count: int = 0
    image_notes: List[str] = Field(default_factory=list)
    processing_notes: List[str] = Field(default_factory=list)


# ---------------------------
# SLIDE MODELS
# ---------------------------

class Slide(BaseModel):
    slide_title: str
    bullets: List[str]
    speaker_notes: Optional[str] = ""
    image_refs: List[str] = Field(default_factory=list)


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


class SlideRequest(BaseModel):
    document_id: str
    n_slides: int = 5
    generate_images: bool = False
    image_style: str = "educational illustration"
    max_generated_images: int = 3

    @model_validator(mode="after")
    def validate_image_generation(self):
        self.max_generated_images = min(max(self.max_generated_images, 0), 10)
        return self


# ---------------------------
# QUIZ MODELS
# ---------------------------

Difficulty = Literal["easy", "medium", "hard"]
QType = Literal["mcq", "short_answer"]


class QuizRequest(BaseModel):
    document_id: str
    difficulty: Difficulty = "medium"
    n_questions: int = 5  # ✅ ADDED


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
