"""High-level indexing pipeline (parsed document -> vector store)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List

from app.models.documents import DocumentMetadata, LocalDocumentInfo, ParsedDocument, Section
from app.models.rag import IndexingResult
from app.services.document_processing.pipeline import parse_document
from app.services.knowledge.chunking import chunk_document
from app.services.knowledge.chunking_config import get_chunking_config, save_chunking_config
from app.services.knowledge.vector_store import LocalVectorStore
from app.storage.files import get_knowledge_base_dir, get_vector_store_path


def _slugify(value: str) -> str:
    clean = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    return "_".join(part for part in clean.split("_") if part) or "document"


_KNOWN_SUFFIXES = frozenset({".txt", ".md", ".json", ".pdf", ".docx", ".pptx"})


def _unique_document_id(path: Path) -> str:
    """Stable unique id per file path (avoids every PDF becoming ``doc_1``)."""
    stem = _slugify(path.stem) or "doc"
    digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:10]
    return f"{stem}_{digest}"


def list_local_document_infos_light() -> List[LocalDocumentInfo]:
    """List knowledge-base files **without** parsing PDFs/DOCX (fast — for API ``GET /documents/local``)."""
    out: List[LocalDocumentInfo] = []
    knowledge_base_dir = get_knowledge_base_dir()
    for path in sorted(knowledge_base_dir.iterdir()):
        if not path.is_file():
            continue
        suf = path.suffix.lower()
        if suf not in _KNOWN_SUFFIXES:
            continue
        out.append(
            LocalDocumentInfo(
                document_id=_unique_document_id(path),
                title=path.stem,
                path=str(path.resolve()),
                filetype=suf.lstrip(".") or "bin",
            )
        )
    return out


def resolve_path_for_document_id(document_id: str) -> Path | None:
    """Map a ``document_id`` to a file path without parsing."""
    knowledge_base_dir = get_knowledge_base_dir()
    for path in sorted(knowledge_base_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _KNOWN_SUFFIXES:
            continue
        if _unique_document_id(path) == document_id:
            return path
    return None


def _build_text_document(path: Path, title: str, text: str) -> ParsedDocument:
    body = (text or "").strip()
    return ParsedDocument(
        document_id=_slugify(path.stem),
        title=title,
        metadata=DocumentMetadata(
            filename=path.name,
            filetype=path.suffix.lstrip(".").lower() or "txt",
            total_pages=1,
            source_path=str(path),
            text_extracted=bool(body),
        ),
        sections=[
            Section(
                section_id="section_1",
                heading="Content",
                level=1,
                page_start=1,
                page_end=1,
                text=body,
            )
        ],
        tables=[],
        images=[],
        full_text=body,
    )


def _load_structured_json(path: Path) -> ParsedDocument:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "document_id" in payload and "sections" in payload:
        if not payload.get("full_text"):
            secs = payload.get("sections") or []
            payload["full_text"] = "\n\n".join(
                (s.get("text") or "") if isinstance(s, dict) else getattr(s, "text", "")
                for s in secs
            ).strip()
        return ParsedDocument(**payload)

    title = payload.get("title") or path.stem
    text = payload.get("text") or payload.get("content") or json.dumps(payload, ensure_ascii=False)
    return _build_text_document(path, title, text)


def parse_local_document(path: Path) -> ParsedDocument:
    suffix = path.suffix.lower()
    if suffix == ".json":
        doc = _load_structured_json(path)
    elif suffix in {".pdf", ".docx", ".pptx"}:
        doc = parse_document(path)
    else:
        doc = _build_text_document(path, path.stem, path.read_text(encoding="utf-8"))

    return doc.model_copy(update={"document_id": _unique_document_id(path)})


def load_local_documents() -> List[ParsedDocument]:
    knowledge_base_dir = get_knowledge_base_dir()
    documents: List[ParsedDocument] = []

    for path in sorted(knowledge_base_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _KNOWN_SUFFIXES:
            continue

        try:
            documents.append(parse_local_document(path))
        except Exception as exc:
            print(f"Skipping document {path}: {exc}")

    return documents


def get_local_document_by_id(document_id: str) -> ParsedDocument | None:
    """Parse **only** the matching file (fast path — does not parse the whole library)."""
    path = resolve_path_for_document_id(document_id)
    if path is None:
        return None
    try:
        return parse_local_document(path)
    except Exception:
        return None


def index_knowledge_base(
    clear_first: bool = True,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> IndexingResult:
    documents = load_local_documents()
    store = LocalVectorStore()

    if chunk_size is not None or chunk_overlap is not None:
        current_config = get_chunking_config()
        effective_chunk_size = chunk_size if chunk_size is not None else current_config.chunk_size
        effective_chunk_overlap = chunk_overlap if chunk_overlap is not None else current_config.chunk_overlap
        save_chunking_config(effective_chunk_size, effective_chunk_overlap)

    if clear_first:
        store.clear()

    total_chunks = 0
    for document in documents:
        try:
            total_chunks += store.add_chunks(chunk_document(document))
        except Exception as exc:
            print(f"Skipping chunk/index for {document.document_id}: {exc}")

    return IndexingResult(
        indexed_documents=len(documents),
        indexed_chunks=total_chunks,
        vector_store_path=str(get_vector_store_path()),
    )
