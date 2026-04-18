"""Chunking strategies for turning parsed documents into embedding-ready chunks."""

"""angelas part"""

from __future__ import annotations

from typing import List

from app.models.documents import ParsedDocument
from app.models.rag import RAGChunk
from app.services.knowledge.chunking_config import get_chunking_config


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []

    config = get_chunking_config()
    chunk_size = chunk_size or config.chunk_size
    overlap = overlap or config.chunk_overlap
    if overlap >= chunk_size:
        overlap = 0

    chunks: List[str] = []
    start = 0

    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            last_space = text.rfind(" ", start, end)
            if last_space > start + 100:
                end = last_space

        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return chunks


def chunk_document(document: ParsedDocument) -> List[RAGChunk]:
    rag_chunks: List[RAGChunk] = []
    chunk_index = 0

    for section in document.sections:
        for piece in chunk_text(section.text):
            rag_chunks.append(
                RAGChunk(
                    chunk_id=f"{document.document_id}_chunk_{chunk_index}",
                    document_id=document.document_id,
                    document_title=document.title,
                    chunk_text=piece,
                    chunk_index=chunk_index,
                    section_heading=section.heading or None,
                    source_path=document.metadata.source_path,
                    metadata={
                        "section_id": section.section_id,
                        "page_start": str(section.page_start),
                        "page_end": str(section.page_end),
                    },
                )
            )
            chunk_index += 1

    for table in document.tables:
        table_text = f"Table: {table.caption or 'No caption'}\n{table.text}".strip()
        for piece in chunk_text(table_text):
            rag_chunks.append(
                RAGChunk(
                    chunk_id=f"{document.document_id}_chunk_{chunk_index}",
                    document_id=document.document_id,
                    document_title=document.title,
                    chunk_text=piece,
                    chunk_index=chunk_index,
                    section_heading=table.caption or "Table",
                    source_path=document.metadata.source_path,
                    metadata={
                        "source_type": "table",
                        "table_id": table.table_id,
                        "page": str(table.page),
                    },
                )
            )
            chunk_index += 1

    for image in document.images:
        image_parts = []
        if image.caption:
            image_parts.append(f"Caption: {image.caption}")
        if image.description:
            image_parts.append(f"Description: {image.description}")
        elif image.asset_path:
            image_parts.append("Description: Visual asset extracted, but no OCR text was available.")
        image_text = "\n".join(image_parts).strip()
        if not image_text:
            continue

        formatted_image_text = f"Image\n{image_text}"
        for piece in chunk_text(formatted_image_text):
            rag_chunks.append(
                RAGChunk(
                    chunk_id=f"{document.document_id}_chunk_{chunk_index}",
                    document_id=document.document_id,
                    document_title=document.title,
                    chunk_text=piece,
                    chunk_index=chunk_index,
                    section_heading=image.caption or "Image",
                    source_path=document.metadata.source_path,
                    metadata={
                        "source_type": "image",
                        "image_id": image.image_id,
                        "page": str(image.page),
                    },
                )
            )
            chunk_index += 1

    return rag_chunks
