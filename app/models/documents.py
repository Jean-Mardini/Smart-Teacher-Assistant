"""Data models for uploaded and parsed documents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    filename: str
    filetype: str
    source_path: Optional[str] = None
    total_pages: int = 1
    extra: Dict[str, Any] = Field(default_factory=dict)


class Section(BaseModel):
    section_id: str
    heading: str = ""
    level: int = 1
    page_start: int = 1
    page_end: int = 1
    text: str


class Table(BaseModel):
    table_id: str
    page: int = 1
    caption: Optional[str] = None
    text: str


class Image(BaseModel):
    image_id: str
    page: int = 1
    caption: Optional[str] = None
    description: Optional[str] = None
    asset_path: Optional[str] = None


class ParsedDocument(BaseModel):
    document_id: str
    title: str
    metadata: DocumentMetadata
    sections: List[Section] = Field(default_factory=list)
    tables: List[Table] = Field(default_factory=list)
    images: List[Image] = Field(default_factory=list)


class LocalDocumentInfo(BaseModel):
    document_id: str
    title: str
    path: str
    filetype: str


class DocumentUploadResult(BaseModel):
    filename: str
    stored_path: str
    filetype: str
