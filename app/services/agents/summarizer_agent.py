"""Summarizer agent implementation (owned by Angela)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from app.models.agents import SummaryResult
from app.services.knowledge.chunking import chunk_text
from app.services.llm.groq_client import call_llm_json

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "summarize.md"

LATEX_OCR_DESC_PREFIX = "LaTeX (OCR):"

MAX_SUMMARY_DOCUMENTS = 10
MAX_SUMMARY_PAGES = 250
MAX_SUMMARY_CHARS = 250_000
# Larger chunks = fewer Groq round-trips (still safe for llama-3.x context on Groq).
SUMMARY_CHUNK_SIZE = int(os.getenv("SUMMARY_CHUNK_SIZE", "20000"))
SUMMARY_CHUNK_OVERLAP = int(os.getenv("SUMMARY_CHUNK_OVERLAP", "800"))
REDUCTION_CHUNK_SIZE = int(os.getenv("REDUCTION_CHUNK_SIZE", "22000"))
REDUCTION_CHUNK_OVERLAP = int(os.getenv("REDUCTION_CHUNK_OVERLAP", "800"))
# Parallel partial summarization (independent API calls); cap to avoid rate-limit bursts.
SUMMARY_MAX_PARALLEL = max(1, min(int(os.getenv("SUMMARY_MAX_PARALLEL", "4")), 12))


def _normalize_documents(doc_json: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(doc_json, list):
        return doc_json
    return [doc_json]


def _format_table(table: dict[str, Any]) -> str:
    page = table.get("page", "?")
    caption = table.get("caption") or "No caption"
    text = table.get("text") or ""
    return f"Table (page {page})\nCaption: {caption}\n{text}".strip()


def _format_image(image: dict[str, Any], image_notes: list[str]) -> str:
    page = image.get("page", "?")
    caption = (image.get("caption") or "").strip()
    description = (image.get("description") or "").strip()
    asset_path = (image.get("asset_path") or image.get("path") or "").strip()

    if not caption and not description and not asset_path:
        image_notes.append(
            f"Image on page {page} had no caption or description, so it could not be summarized reliably."
        )
        return ""

    parts = [f"Image (page {page})"]
    if caption:
        parts.append(f"Caption: {caption}")
    if description:
        parts.append(f"Description/OCR: {description}")
    elif asset_path:
        parts.append("Visual asset extracted, but no OCR text was available.")
    return "\n".join(parts)


def _build_document_text(document_json: dict[str, Any], image_notes: list[str]) -> str:
    parts: list[str] = []

    for section in document_json.get("sections", []):
        heading = section.get("heading", "")
        content = section.get("text", "")
        page_start = section.get("page_start", "?")
        page_end = section.get("page_end", page_start)
        label = f"Section (pages {page_start}-{page_end})"
        if heading:
            label = f"{label}: {heading}"
        parts.append(f"{label}\n{content}".strip())

    for table in document_json.get("tables", []):
        formatted_table = _format_table(table)
        if formatted_table:
            parts.append(formatted_table)

    for image in document_json.get("images", []):
        formatted_image = _format_image(image, image_notes)
        if formatted_image:
            parts.append(formatted_image)

    return "\n\n".join(part for part in parts if part.strip())


def _normalize_formula_key(s: str) -> str:
    return " ".join(s.split())


def _extract_latex_ocr_formulas(documents: list[dict[str, Any]]) -> list[str]:
    """Pull LaTeX strings from PDF formula-OCR image descriptions (see ``formula_ocr``)."""
    seen: set[str] = set()
    out: list[str] = []
    for doc in documents:
        for img in doc.get("images") or []:
            if not isinstance(img, dict):
                continue
            desc = (img.get("description") or "").strip()
            if not desc.startswith(LATEX_OCR_DESC_PREFIX):
                continue
            latex = desc[len(LATEX_OCR_DESC_PREFIX) :].strip()
            if latex.startswith("`") and latex.endswith("`") and len(latex) >= 2:
                latex = latex[1:-1].strip()
            key = _normalize_formula_key(latex)
            if key and key not in seen:
                seen.add(key)
                out.append(latex)
    return out


def _merge_formula_lists(ocr_list: list[str], llm_list: object) -> list[str]:
    """Prefer OCR order; append LLM-only strings that are not duplicates."""
    merged: list[str] = list(ocr_list)
    seen = {_normalize_formula_key(x) for x in merged}
    if not isinstance(llm_list, list):
        return merged
    for raw in llm_list:
        s = str(raw).strip()
        if not s:
            continue
        key = _normalize_formula_key(s)
        if key and key not in seen:
            seen.add(key)
            merged.append(s)
    return merged


def _build_combined_text(documents: list[dict[str, Any]], image_notes: list[str]) -> tuple[str, list[str], int]:
    blocks: list[str] = []
    source_documents: list[str] = []
    total_pages = 0

    for index, document in enumerate(documents, start=1):
        title = document.get("title", f"Document {index}")
        source_documents.append(title)
        total_pages += int(document.get("metadata", {}).get("total_pages", 0) or 0)

        document_text = _build_document_text(document, image_notes)
        if not document_text.strip():
            continue

        block = (
            f"DOCUMENT {index}\n"
            f"Title: {title}\n"
            f"Document ID: {document.get('document_id', f'doc_{index}')}\n"
            f"{document_text}"
        )
        blocks.append(block)

    return "\n\n".join(blocks), source_documents, total_pages


def _summary_length_instruction(length: str) -> str:
    length_map = {
        "short": "maximum 80 words",
        "medium": "maximum 150 words",
        "long": "maximum 250 words",
    }
    return length_map.get(length, "maximum 150 words")


def _call_summary_prompt(prompt: str, title: str, text: str) -> dict[str, Any]:
    reference_note = (
        "If the document includes inline references like [1], [2], or [3], "
        "keep those markers exactly as written in the generated summary and key points. "
        "Do not add new references and do not renumber existing ones."
    )

    system = "You output strict JSON only."
    user = f"""
{prompt}

REFERENCE HANDLING:
{reference_note}

TITLE:
{title}

TEXT:
{text}
"""
    data = call_llm_json(system, user)
    data.setdefault("action_items", [])
    data.setdefault("formulas", [])
    data.setdefault("glossary", [])
    data.setdefault("key_points", [])
    data.setdefault("summary", "")
    return data


def _serialize_partial(index: int, partial: dict[str, Any]) -> str:
    return (
        f"PARTIAL SUMMARY {index}\n"
        f"{json.dumps(partial, ensure_ascii=False, indent=2)}"
    )


def _collect_processing_notes(
    documents: list[dict[str, Any]],
    combined_text: str,
    chunk_count: int,
    image_notes: list[str],
) -> list[str]:
    notes: list[str] = []
    section_count = sum(len(doc.get("sections", [])) for doc in documents)
    table_count = sum(len(doc.get("tables", [])) for doc in documents)
    image_count = sum(len(doc.get("images", [])) for doc in documents)

    if len(documents) > 1:
        notes.append(f"Combined {len(documents)} documents into one summary request.")
    if chunk_count > 1:
        notes.append(f"Used hierarchical summarization across {chunk_count} chunks for long input.")
    else:
        notes.append("Processed the source text in a single summarization pass.")

    notes.append(
        f"Processed approximately {len(combined_text)} characters across "
        f"{section_count} sections, {table_count} tables, and {image_count} images."
    )

    if image_notes:
        notes.append("Included image captions/descriptions when available and flagged images without textual context.")
    else:
        notes.append("No image metadata was available to influence the summary.")

    return notes


def _validate_limits(documents: list[dict[str, Any]], total_pages: int, combined_text: str) -> None:
    if len(documents) > MAX_SUMMARY_DOCUMENTS:
        raise ValueError(
            f"You can summarize up to {MAX_SUMMARY_DOCUMENTS} documents at once."
        )
    if total_pages > MAX_SUMMARY_PAGES:
        raise ValueError(
            f"The current summarizer supports up to {MAX_SUMMARY_PAGES} pages per request."
        )
    if len(combined_text) > MAX_SUMMARY_CHARS:
        raise ValueError(
            f"The current summarizer supports up to {MAX_SUMMARY_CHARS} characters of extracted content per request."
        )


async def _synthesize_long_input(
    prompt: str,
    title: str,
    combined_text: str,
) -> tuple[dict[str, Any], int]:
    base_chunks = chunk_text(
        combined_text,
        chunk_size=SUMMARY_CHUNK_SIZE,
        overlap=SUMMARY_CHUNK_OVERLAP,
    )

    sem = asyncio.Semaphore(SUMMARY_MAX_PARALLEL)

    async def _partial(index: int, piece: str) -> dict[str, Any]:
        partial_title = f"{title} - chunk {index}/{len(base_chunks)}"
        async with sem:
            return await asyncio.to_thread(_call_summary_prompt, prompt, partial_title, piece)

    partial_summaries = await asyncio.gather(
        *[_partial(i, p) for i, p in enumerate(base_chunks, start=1)]
    )

    serialized = "\n\n".join(
        _serialize_partial(index, partial)
        for index, partial in enumerate(partial_summaries, start=1)
    )

    reduction_chunks = chunk_text(
        serialized,
        chunk_size=REDUCTION_CHUNK_SIZE,
        overlap=REDUCTION_CHUNK_OVERLAP,
    )

    if len(reduction_chunks) == 1:
        final_data = await asyncio.to_thread(
            _call_summary_prompt,
            prompt,
            f"{title} - final synthesis",
            reduction_chunks[0],
        )
        return final_data, len(base_chunks)

    async def _reduction(index: int, piece: str) -> dict[str, Any]:
        reduction_title = f"{title} - reduction {index}/{len(reduction_chunks)}"
        async with sem:
            return await asyncio.to_thread(_call_summary_prompt, prompt, reduction_title, piece)

    reduction_partials = await asyncio.gather(
        *[_reduction(i, p) for i, p in enumerate(reduction_chunks, start=1)]
    )

    final_serialized = "\n\n".join(
        _serialize_partial(index, partial)
        for index, partial in enumerate(reduction_partials, start=1)
    )
    final_data = await asyncio.to_thread(
        _call_summary_prompt,
        prompt,
        f"{title} - final synthesis",
        final_serialized,
    )
    return final_data, len(base_chunks)


async def run_summarizer(
    doc_json: dict[str, Any] | list[dict[str, Any]],
    length: str = "medium",
) -> SummaryResult:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt.replace("{SUMMARY_LENGTH}", _summary_length_instruction(length))

    documents = _normalize_documents(doc_json)
    image_notes: list[str] = []
    combined_text, source_documents, total_pages = _build_combined_text(documents, image_notes)

    if not combined_text.strip():
        return SummaryResult(
            summary="",
            key_points=[],
            action_items=[],
            formulas=[],
            glossary=[],
            source_documents=source_documents,
            total_pages=total_pages,
            chunk_count=0,
            image_notes=image_notes,
            processing_notes=["No textual content was extracted from the selected document(s)."],
        )

    _validate_limits(documents, total_pages, combined_text)

    title = source_documents[0] if len(source_documents) == 1 else "Multi-document summary"
    chunk_candidates = chunk_text(
        combined_text,
        chunk_size=SUMMARY_CHUNK_SIZE,
        overlap=SUMMARY_CHUNK_OVERLAP,
    )

    if len(chunk_candidates) <= 1:
        data = await asyncio.to_thread(_call_summary_prompt, prompt, title, combined_text)
        chunk_count = 1
    else:
        data, chunk_count = await _synthesize_long_input(prompt, title, combined_text)

    processing_notes = _collect_processing_notes(
        documents,
        combined_text,
        chunk_count,
        image_notes,
    )

    data.setdefault("action_items", [])
    data.setdefault("formulas", [])
    data.setdefault("glossary", [])
    data.setdefault("key_points", [])
    data.setdefault("summary", "")
    ocr_formulas = _extract_latex_ocr_formulas(documents)
    data["formulas"] = _merge_formula_lists(ocr_formulas, data.get("formulas"))
    data["source_documents"] = source_documents
    data["total_pages"] = total_pages
    data["chunk_count"] = chunk_count
    data["image_notes"] = image_notes
    data["processing_notes"] = processing_notes

    return SummaryResult.model_validate(data)
