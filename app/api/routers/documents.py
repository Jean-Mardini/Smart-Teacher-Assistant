"""Routers for document-related endpoints (upload, list, inspect)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.documents import DocumentUploadResult, LocalDocumentInfo
from app.services.knowledge.indexing_pipeline import list_local_document_infos_light
from app.storage.files import get_knowledge_base_dir, sanitize_filename

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".txt", ".md", ".json", ".pdf", ".docx", ".pptx"}


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

        safe_name = sanitize_filename(original_name)
        target_path = knowledge_base_dir / safe_name

        counter = 1
        while target_path.exists():
            stem = Path(safe_name).stem
            ext = Path(safe_name).suffix
            target_path = knowledge_base_dir / f"{stem}_{counter}{ext}"
            counter += 1

        content = await upload.read()
        target_path.write_bytes(content)

        results.append(
            DocumentUploadResult(
                filename=target_path.name,
                stored_path=str(target_path),
                filetype=suffix.lstrip("."),
            )
        )

    return results
