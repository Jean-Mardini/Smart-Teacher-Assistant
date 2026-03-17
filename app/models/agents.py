"""Data models describing inputs and outputs for all agents.

Each agent (summarizer, quiz, slides, rubric, grading, chat, cross-doc)
will have request/response models defined here.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal


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
    document_id: str
    length: SummaryLength = "medium"


class GlossaryItem(BaseModel):
    term: str
    definition: str


class SummaryResult(BaseModel):
    summary: str
    key_points: List[str]
    action_items: Optional[List[str]] = Field(default_factory=list)
    glossary: Optional[List[GlossaryItem]] = Field(default_factory=list)


# ---------------------------
# SLIDE MODELS
# ---------------------------

class Slide(BaseModel):
    slide_title: str
    bullets: List[str]
    speaker_notes: Optional[str] = ""


class SlideDeckResult(BaseModel):
    title: str
    slides: List[Slide]


class SlideRequest(BaseModel):
    document_id: str
    n_slides: int = 5


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