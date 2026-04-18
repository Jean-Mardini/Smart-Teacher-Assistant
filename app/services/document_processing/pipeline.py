"""High-level document processing pipeline (upload -> parse -> structured JSON)."""

"""angelas part"""

from __future__ import annotations

from pathlib import Path

from app.models.documents import ParsedDocument
from app.services.document_processing.docx_parser import parse_docx
from app.services.document_processing.pdf_parser import parse_pdf
from app.services.document_processing.pptx_parser import parse_pptx


def parse_document(path: str | Path) -> ParsedDocument:
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return parse_pdf(file_path)
    if suffix == ".docx":
        return parse_docx(file_path)
    if suffix == ".pptx":
        return parse_pptx(file_path)

    raise ValueError(f"Unsupported document type: {file_path.suffix}")
