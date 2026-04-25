import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import fitz
from langdetect import detect

from app.models.documents import DocumentMetadata, ParsedDocument
from .formula_ocr import enrich_pdf_images_with_formula_latex
from .pdf_parser import extract_pdf_text, extract_pdf_images
from .docx_parser import extract_docx_text
from .pptx_parser import extract_pptx_text
from .tables import extract_pdf_tables
from .structure_extraction import split_into_sections

_SUPPORTED = {".pdf", ".docx", ".pptx"}

logger = logging.getLogger(__name__)


def _reload_project_dotenv() -> None:
    """Re-read ``.env`` so flags like ``PDF_FORMULA_OCR`` apply without restarting the API."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[3]
    load_dotenv(root / ".env", override=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_pdf_spans(filepath: str) -> List[Dict[str, Any]]:
    """Extract per-line font metadata from a PDF via PyMuPDF's dict mode.

    Returns a list of ``{"text": str, "size": float, "bold": bool, "page": int}``
    consumed by :func:`split_into_sections` for font-size-aware heading detection.

    Failures are logged and return an empty list so the pipeline degrades
    gracefully to text-only heading detection.
    """
    result: List[Dict[str, Any]] = []
    try:
        doc = fitz.open(filepath)
        for page_num, page in enumerate(doc, start=1):
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:  # 0 = text block
                    continue
                for fitz_line in block.get("lines", []):
                    spans = fitz_line.get("spans", [])
                    if not spans:
                        continue
                    line_text = "".join(s.get("text", "") for s in spans).strip()
                    if not line_text:
                        continue
                    # Max size in the line drives heading-level assignment
                    max_size = max(s.get("size", 12.0) for s in spans)
                    # PyMuPDF flag bit 4 (value 16) = bold
                    is_bold = any(bool(s.get("flags", 0) & 16) for s in spans)
                    result.append(
                        {
                            "text": line_text,
                            "size": max_size,
                            "bold": is_bold,
                            "page": page_num,
                        }
                    )
        doc.close()
    except Exception as exc:
        logger.warning("Span extraction skipped for %s: %s", filepath, exc)
    return result


def _detect_language(text: str) -> str:
    """Return ISO 639-1 language code, or ``'unknown'`` on failure.

    Only the first 5 000 characters are sampled for speed; this is enough
    for reliable detection on EN, FR, and AR documents.
    """
    try:
        return detect(text[:5000])
    except Exception:
        return "unknown"


def _pick_title(sections: list, full_text: str, filename: str) -> str:
    """Select the document title using a priority chain.

    1. First h1 section heading (most authoritative).
    2. First non-empty line of the full text.
    3. Filename stem (safe fallback).
    """
    for sec in sections:
        if sec.get("level") == 1 and sec.get("heading"):
            return sec["heading"]
    first_line = next(
        (line.strip() for line in full_text.splitlines() if line.strip()), ""
    )
    if first_line:
        return first_line
    return os.path.splitext(filename)[0]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_document(
    filepath: str,
    document_number: int = 1,
    on_progress: Optional[Callable[[str, float], None]] = None,
) -> ParsedDocument:
    """Full document processing pipeline.

    No LLM calls — purely deterministic extraction.

    Parameters
    ----------
    filepath:
        Path to a ``.pdf``, ``.docx``, or ``.pptx`` file.
    document_number:
        Integer suffix for ``document_id`` (``1`` → ``"doc_1"``).
    on_progress:
        Optional ``callback(step: str, fraction: float)`` fired at each
        pipeline stage.  *fraction* is in ``[0.0, 1.0]``.

    Returns
    -------
    :class:`~app.models.documents.ParsedDocument`
    """
    _reload_project_dotenv()
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filepath)[1].lower()

    if ext not in _SUPPORTED:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(_SUPPORTED))}"
        )

    def _progress(step: str, frac: float) -> None:
        logger.info("[%s] %s (%.0f%%)", filename, step, frac * 100)
        if on_progress:
            on_progress(step, frac)

    # -----------------------------------------------------------------------
    # Stage 1 — Load
    #
    # PDF: text extraction, table extraction, and span extraction are fully
    # independent reads of the same file → run all three in parallel.
    #
    # DOCX / PPTX: tables are extracted in the same pass as text (the parsers
    # iterate document structure once), so no parallelism is gained there.
    # -----------------------------------------------------------------------
    _progress("loading", 0.0)

    line_meta: Optional[List[Dict[str, Any]]] = None

    document_id = f"doc_{document_number}"

    if ext == ".pdf":
        with ThreadPoolExecutor(max_workers=4) as pool:
            fut_text   = pool.submit(extract_pdf_text,   filepath)
            fut_tables = pool.submit(extract_pdf_tables, filepath)
            fut_spans  = pool.submit(_extract_pdf_spans, filepath)
            fut_images = pool.submit(extract_pdf_images, filepath, document_id)

        pages, full_text, ocr_attempted = fut_text.result()
        tables                         = fut_tables.result()
        line_meta                      = fut_spans.result()
        images                         = fut_images.result()
        if images:
            images = enrich_pdf_images_with_formula_latex(images)

    elif ext == ".docx":
        pages, full_text, tables, images = extract_docx_text(filepath, document_id=document_id)
        ocr_attempted = False

    else:  # .pptx
        pages, full_text, tables, images = extract_pptx_text(filepath, document_id=document_id)
        ocr_attempted = False

    _progress("loaded", 0.45)

    # -----------------------------------------------------------------------
    # Stage 2 — Language detection
    # Fast (samples first 5 000 chars); done before structure extraction so
    # language can be stored in metadata without blocking the heavier work.
    # -----------------------------------------------------------------------
    _progress("detecting language", 0.50)
    language = _detect_language(full_text)

    # -----------------------------------------------------------------------
    # Stage 3 — Structure extraction
    # For PDF, passes line_meta so font size and bold flags drive heading levels.
    # For DOCX / PPTX, line_meta is None → falls back to text-only heuristics.
    # -----------------------------------------------------------------------
    _progress("extracting structure", 0.60)
    sections = split_into_sections(full_text, pages=pages, line_meta=line_meta)

    # -----------------------------------------------------------------------
    # Stage 3b — Drop sections whose headings are table cell values
    #
    # Table row-header strings (e.g. "Implementation", "Connectivity") are
    # detected as h2/h3 headings by the text heuristics because they look like
    # short title-case phrases.  After we know which tables exist we can build
    # an exact-match blocklist from every cell in every table and prune those
    # false sections.
    # -----------------------------------------------------------------------
    if tables:
        _table_cells: set = set()
        for _tbl in tables:
            for _line in _tbl.get("text", "").split("\n"):
                # Skip the separator line ("----...")
                if re.match(r"^-+$", _line.strip()):
                    continue
                for _cell in _line.split(" | "):
                    _val = _cell.strip()
                    if _val:
                        _table_cells.add(_val)
        sections = [s for s in sections if s.get("heading") not in _table_cells]

    # -----------------------------------------------------------------------
    # Stage 4 — Assemble ParsedDocument
    # -----------------------------------------------------------------------
    _progress("assembling document", 0.90)

    metadata = DocumentMetadata(
        filename=filename,
        filetype=ext.lstrip("."),
        total_pages=len(pages),
        language=language,
        ocr_attempted=ocr_attempted,
        text_extracted=bool(full_text.strip()),
    )

    parsed = ParsedDocument(
        document_id=document_id,
        title=_pick_title(sections, full_text, filename),
        metadata=metadata,
        sections=sections,
        tables=tables,
        images=images,
        full_text=full_text,
    )

    _progress("done", 1.0)
    return parsed


def parse_document(path: Union[str, Path], document_number: int = 1) -> ParsedDocument:
    """Compatibility wrapper for :func:`process_document` (indexing + agents)."""
    return process_document(str(path), document_number=document_number)
