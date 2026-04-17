from pydantic import BaseModel
from typing import List, Optional


class Section(BaseModel):
    section_id: str
    heading: str
    level: int
    page_start: int
    page_end: Optional[int]
    text: str


class Table(BaseModel):
    table_id: str
    page: int
    caption: str
    text: str


class Image(BaseModel):
    image_id: str
    page: int
    caption: str
    path: str


class DocumentMetadata(BaseModel):
    filename: str
    filetype: str
    total_pages: int
    language: Optional[str] = "en"
    ocr_attempted: bool = False
    text_extracted: bool = True


class ParsedDocument(BaseModel):
    document_id: str
    title: str
    metadata: DocumentMetadata

    sections: List[Section] = []
    tables: List[Table] = []
    images: List[Image] = []

    full_text: str
