"""Data models for uploaded and parsed documents (Matheos pipeline + API helpers)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Section(BaseModel):
    section_id: str
    heading: str = ""
    level: int = 1
    page_start: int = 1
    page_end: Optional[int] = None
    text: str = ""


class Table(BaseModel):
    table_id: str
    page: int = 1
    caption: str = ""
    text: str = ""


class Image(BaseModel):
    image_id: str
    page: int = 1
    caption: str = ""
    path: str = ""
    # Populated when PDF_FORMULA_OCR=1 and pix2tex can read equation-like bitmaps (summarizer / RAG use this).
    description: str = ""


class DocumentMetadata(BaseModel):
    filename: str
    filetype: str
    total_pages: int = 1
    language: Optional[str] = "en"
    ocr_attempted: bool = False
    text_extracted: bool = True
    source_path: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    document_id: str
    title: str
    metadata: DocumentMetadata
    sections: List[Section] = Field(default_factory=list)
    tables: List[Table] = Field(default_factory=list)
    images: List[Image] = Field(default_factory=list)
    full_text: str = ""


class LocalDocumentInfo(BaseModel):
    document_id: str
    title: str
    path: str
    filetype: str


class DocumentUploadResult(BaseModel):
    filename: str
    stored_path: str
    filetype: str
