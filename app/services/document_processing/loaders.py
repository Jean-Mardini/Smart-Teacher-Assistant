import os

from .pdf_parser import extract_pdf_text
from .docx_parser import extract_docx_text
from .pptx_parser import extract_pptx_text
from .tables import extract_pdf_tables

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx"}


def load_document(filepath: str):
    """
    Load a document and return (pages, full_text, ext, tables).

    Supported formats:
        .pdf   — text extraction with OCR fallback, header/footer removal
        .docx  — paragraph text + native table extraction
        .pptx  — slide text + table extraction + speaker notes
    """

    ext = os.path.splitext(filepath)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext == ".pdf":
        pages, full_text = extract_pdf_text(filepath)
        tables = extract_pdf_tables(filepath)

    elif ext == ".docx":
        pages, full_text, tables = extract_docx_text(filepath)

    elif ext == ".pptx":
        pages, full_text, tables = extract_pptx_text(filepath)

    return pages, full_text, ext, tables
