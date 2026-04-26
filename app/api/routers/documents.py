"""Routers for document-related endpoints (upload, list, inspect, delete)."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.documents import DocumentUploadResult, LocalDocumentInfo
from app.services.knowledge.indexing_pipeline import (
    invalidate_doc_cache,
    list_local_document_infos_light,
    resolve_path_for_document_id,
)
from app.storage.files import get_knowledge_base_dir, sanitize_filename

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".txt", ".md", ".json", ".pdf", ".docx", ".pptx"}


def _find_duplicate(directory: Path, content_hash: str) -> Path | None:
    """Return path of an existing file whose content matches the given SHA-256 hash."""
    for f in directory.iterdir():
        if f.is_file():
            try:
                if hashlib.sha256(f.read_bytes()).hexdigest() == content_hash:
                    return f
            except Exception:
                continue
    return None


@router.get("/local", response_model=list[LocalDocumentInfo])
async def list_local_documents():
    # Fast path: do not parse every PDF on each request
    return list_local_document_infos_light()


@router.post("/upload", response_model=list[DocumentUploadResult])
async def upload_documents(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    knowledge_base_dir = get_knowledge_base_dir()
    results: list[DocumentUploadResult] = []

    for upload in files:
        original_name = upload.filename or "document"
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type for '{original_name}'.",
            )

        content = await upload.read()
        content_hash = hashlib.sha256(content).hexdigest()

        # Skip saving if an identical file already exists in the library
        existing = await asyncio.to_thread(_find_duplicate, knowledge_base_dir, content_hash)
        if existing is not None:
            results.append(
                DocumentUploadResult(
                    filename=existing.name,
                    stored_path=str(existing),
                    filetype=existing.suffix.lower().lstrip("."),
                )
            )
            continue

        safe_name = sanitize_filename(original_name)
        target_path = knowledge_base_dir / safe_name

        counter = 1
        while target_path.exists():
            stem = Path(safe_name).stem
            ext = Path(safe_name).suffix
            target_path = knowledge_base_dir / f"{stem}_{counter}{ext}"
            counter += 1

        await asyncio.to_thread(target_path.write_bytes, content)
        invalidate_doc_cache()

        results.append(
            DocumentUploadResult(
                filename=target_path.name,
                stored_path=str(target_path),
                filetype=suffix.lstrip("."),
            )
        )

    return results


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str):
    path = await asyncio.to_thread(resolve_path_for_document_id, document_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
    try:
        await asyncio.to_thread(path.unlink)
        invalidate_doc_cache()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {exc}")
