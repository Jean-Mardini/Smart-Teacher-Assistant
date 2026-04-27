"""Summarizer agent implementation (owned by Angela)."""

from __future__ import annotations

import asyncio
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.agents import SummaryResult
from app.services.knowledge.chunking import chunk_text
from app.services.llm.groq_client import call_llm_json

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
PROMPT_PATH = _PROMPTS_DIR / "summarize.md"
PROMPT_MAP_CHUNK_PATH = _PROMPTS_DIR / "summarize_map_chunk.md"
PROMPT_REDUCE_PATH = _PROMPTS_DIR / "summarize_reduce.md"

LATEX_OCR_DESC_PREFIX = "LaTeX (OCR):"


class SummarizerLimitError(ValueError):
    """Input exceeds summarizer page / character / document-count limits."""



MAX_SUMMARY_DOCUMENTS = 10
# Large slide decks exceed the old defaults quickly; override via env if needed.
MAX_SUMMARY_PAGES = int(os.getenv("MAX_SUMMARY_PAGES", "400"))
MAX_SUMMARY_CHARS = int(os.getenv("MAX_SUMMARY_CHARS", "600000"))
# Chunk size: larger chunks mean fewer LLM round-trips (faster). Tune down if Groq returns
# context errors; Groq 128k models usually tolerate ~20–26k chars + prompt for map passes.
SUMMARY_CHUNK_SIZE = int(os.getenv("SUMMARY_CHUNK_SIZE", "22000"))
SUMMARY_CHUNK_OVERLAP = int(os.getenv("SUMMARY_CHUNK_OVERLAP", "900"))
REDUCTION_CHUNK_SIZE = int(os.getenv("REDUCTION_CHUNK_SIZE", "26000"))
REDUCTION_CHUNK_OVERLAP = int(os.getenv("REDUCTION_CHUNK_OVERLAP", "900"))
# Parallel map/reduce calls (huge win vs 1). Set SUMMARY_MAX_PARALLEL=2–3 if you hit Groq TPM 429s.
SUMMARY_MAX_PARALLEL = max(1, min(int(os.getenv("SUMMARY_MAX_PARALLEL", "6")), 12))

# Bracket-style numeric citations only (e.g. [1], [12]); post-process never touches formulas list.
_BRACKET_NUM_REF = re.compile(r"\[(\d+)\]")


def _normalize_documents(doc_json: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(doc_json, list):
        return doc_json
    return [doc_json]


def _coerce_str_list(value: Any) -> list[str]:
    """Turn common LLM mistakes (single string, null, nested values) into ``list[str]``."""
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                t = item.strip()
                if t:
                    out.append(t)
            elif isinstance(item, (int, float)):
                out.append(str(item))
            elif isinstance(item, dict):
                # Prefer a single human-readable line when the model emits objects.
                t = str(item.get("text") or item.get("point") or item.get("item") or "").strip()
                if t:
                    out.append(t)
                else:
                    compact = json.dumps(item, ensure_ascii=False)
                    if compact and compact != "{}":
                        out.append(compact)
        return out
    return [str(value).strip()] if str(value).strip() else []


def _coerce_glossary(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            term = str(item.get("term", "") or "").strip()
            definition = str(item.get("definition", "") or "").strip()
            if term or definition:
                out.append({"term": term, "definition": definition})
        elif isinstance(item, str) and item.strip():
            out.append({"term": item.strip(), "definition": ""})
    return out


def _normalize_summary_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize model output so :class:`SummaryResult` validation rarely fails on shape."""
    merged = dict(data)
    merged["summary"] = str(merged.get("summary") or "")
    merged["key_points"] = _coerce_str_list(merged.get("key_points"))
    merged["action_items"] = _coerce_str_list(merged.get("action_items"))
    merged["formulas"] = _coerce_str_list(merged.get("formulas"))
    merged["glossary"] = _coerce_glossary(merged.get("glossary"))
    return merged


def _allowed_bracket_reference_ids(source_text: str) -> set[str]:
    """Digits ``n`` for markers ``[n]`` appearing in the source (citation-style)."""
    return set(_BRACKET_NUM_REF.findall(source_text or ""))


def _strip_bracket_refs_not_in_allowed(text: str, allowed: set[str]) -> tuple[str, int]:
    if not text or not allowed:
        return text, 0
    removed = 0

    def _sub(m: re.Match[str]) -> str:
        nonlocal removed
        if m.group(1) in allowed:
            return m.group(0)
        removed += 1
        return ""

    out = _BRACKET_NUM_REF.sub(_sub, text)
    if removed:
        out = re.sub(r"  +", " ", out)
    return out, removed


def _apply_reference_marker_postprocess(
    data: dict[str, Any],
    citation_source_text: str,
) -> tuple[dict[str, Any], list[str]]:
    """Remove ``[n]`` markers the model invented when ``n`` never appears in the source."""
    allowed = _allowed_bracket_reference_ids(citation_source_text)
    if not allowed:
        return data, []
    out = dict(data)
    removed_total = 0

    s, n = _strip_bracket_refs_not_in_allowed(str(out.get("summary") or ""), allowed)
    out["summary"] = s
    removed_total += n

    kps: list[str] = []
    for kp in out.get("key_points") or []:
        t, n2 = _strip_bracket_refs_not_in_allowed(str(kp), allowed)
        removed_total += n2
        kps.append(t)
    out["key_points"] = kps

    actions: list[str] = []
    for item in out.get("action_items") or []:
        t, n2 = _strip_bracket_refs_not_in_allowed(str(item), allowed)
        removed_total += n2
        actions.append(t)
    out["action_items"] = actions

    gloss: list[dict[str, str]] = []
    for item in out.get("glossary") or []:
        if not isinstance(item, dict):
            continue
        term, a = _strip_bracket_refs_not_in_allowed(str(item.get("term", "")), allowed)
        defin, b = _strip_bracket_refs_not_in_allowed(str(item.get("definition", "")), allowed)
        removed_total += a + b
        gloss.append({"term": term.strip(), "definition": defin.strip()})
    out["glossary"] = gloss

    extras: list[str] = []
    if removed_total:
        extras.append(
            f"Post-processing removed {removed_total} numeric bracket citation(s) [n] that do not "
            "appear in the combined source text, so only source-backed markers remain."
        )
    return out, extras


def _should_use_rag_summarize(
    use_rag: bool | None,
    num_docs: int,
    combined_len: int,
    total_pages: int = 0,
) -> bool:
    if use_rag is True:
        return True
    if use_rag is False:
        return False
    thr_single = int(os.getenv("SUMMARY_RAG_CHAR_THRESHOLD", "55000"))
    thr_multi = int(os.getenv("SUMMARY_RAG_MULTI_DOC_CHAR_THRESHOLD", "50000"))
    force_pages = max(0, int(os.getenv("SUMMARY_RAG_FORCE_PAGES", "70")))
    if num_docs == 1 and force_pages > 0 and total_pages >= force_pages:
        return True
    if num_docs > 1 and combined_len > thr_multi:
        return True
    if combined_len > thr_single:
        return True
    return False


def _soft_cap_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Trim at a paragraph boundary when possible; append a short notice if truncated."""
    t = (text or "").strip()
    if not t or len(t) <= max_chars:
        return t, False
    cut = t[:max_chars].rstrip()
    br = max(cut.rfind("\n\n"), cut.rfind(". "), int(max_chars * 0.82))
    if br > max_chars // 3:
        cut = cut[:br].rstrip()
    note = (
        "\n\n[… Context truncated for a faster summary; all statements should still follow this text only.]"
    )
    return cut + note, True


def _stratified_excerpt(text: str, max_chars: int) -> str:
    """Head + mid + tail slices when the full document is too large for one model pass."""
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    # Reserve space for markers
    budget = max_chars - 280
    a = budget * 50 // 100
    b = budget * 25 // 100
    c = budget - a - b
    head = t[:a].rstrip()
    mid_start = max((len(t) - b) // 2, 0)
    mid = t[mid_start : mid_start + b].strip()
    tail = t[-max(c, 0) :].strip()
    return (
        f"[BEGIN — {len(t)} characters total]\n{head}\n\n"
        f"[MIDDLE excerpt]\n{mid}\n\n"
        f"[END excerpt]\n{tail}\n\n"
        "[Note: Vector retrieval returned little text; this stratified excerpt replaces the full "
        "document for one fast summarization pass.]"
    )


def _retrieve_summary_context_sync(documents: list[dict[str, Any]], combined_excerpt: str) -> str:
    """Pull top similar chunks from the local index for the selected document ids."""
    ids = [str(d.get("document_id") or "").strip() for d in documents if str(d.get("document_id") or "").strip()]
    if not ids:
        return ""
    titles = [str(d.get("title") or "Document") for d in documents]
    excerpt = (combined_excerpt or "").strip()[:8000]
    query = (
        "Educational materials: themes, definitions, procedures, facts, and references for summarization.\n"
        f"Document titles: {'; '.join(titles)}\n\n"
        f"Representative excerpt:\n{excerpt}"
    )
    top_k = max(4, min(int(os.getenv("SUMMARY_RAG_TOP_K", "28")), 80))
    per_chunk = max(300, min(int(os.getenv("SUMMARY_RAG_CHUNK_CHARS", "1400")), 8000))
    rag_cap = max(8000, min(int(os.getenv("SUMMARY_RAG_INPUT_CAP", "38000")), 200_000))
    from app.services.knowledge.retrieval import Retriever

    retriever = Retriever()
    chunks = retriever.retrieve(query, top_k=top_k, document_ids=ids)
    if not chunks:
        return ""
    parts: list[str] = []
    for c in chunks:
        head = f"---\n[{c.document_title}]"
        sh = getattr(c, "section_heading", None)
        if sh:
            head += f" — {sh}"
        head += "\n"
        body = (getattr(c, "chunk_text", None) or "").strip()
        if len(body) > per_chunk:
            body = body[:per_chunk].rstrip() + "\n[…]"
        parts.append(head + body)
    joined = "\n\n".join(parts).strip()
    capped, _ = _soft_cap_text(joined, rag_cap)
    return capped


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

    structured = "\n\n".join(part for part in parts if part.strip())
    full_text = (document_json.get("full_text") or "").strip()
    if not structured and full_text:
        return full_text
    # Heading detection often yields sparse sections for slide PDFs while ``full_text`` still
    # holds the page stream; prefer the larger extraction when it clearly dominates.
    if full_text and len(full_text) > max(8000, int(len(structured) * 1.5)):
        return full_text
    return structured or full_text


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


@lru_cache(maxsize=1)
def _summarize_prompt_templates() -> tuple[str, str, str]:
    """Full (final), map-chunk, and reduce-phase prompts (cached)."""
    return (
        PROMPT_PATH.read_text(encoding="utf-8"),
        PROMPT_MAP_CHUNK_PATH.read_text(encoding="utf-8"),
        PROMPT_REDUCE_PATH.read_text(encoding="utf-8"),
    )


def _call_map_chunk_prompt(prompt: str, title: str, text: str) -> dict[str, Any]:
    """Lighter prompt for hierarchical map phase (one raw-text chunk)."""
    system = "You output strict JSON only."
    user = f"{prompt}\n\nTITLE:\n{title}\n\nEXCERPT:\n{text}"
    data = call_llm_json(system, user)
    data.setdefault("action_items", [])
    data.setdefault("formulas", [])
    data.setdefault("glossary", [])
    data.setdefault("key_points", [])
    data.setdefault("summary", "")
    return data


def _call_reduce_prompt(prompt: str, title: str, text: str) -> dict[str, Any]:
    """Lighter prompt for merging serialized partial JSON summaries."""
    system = "You output strict JSON only."
    user = f"{prompt}\n\nTITLE:\n{title}\n\nPARTIAL SUMMARIES:\n{text}"
    data = call_llm_json(system, user)
    data.setdefault("action_items", [])
    data.setdefault("formulas", [])
    data.setdefault("glossary", [])
    data.setdefault("key_points", [])
    data.setdefault("summary", "")
    return data


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
    # Compact JSON keeps the reduce / final phases smaller and faster.
    return f"PARTIAL SUMMARY {index}\n{json.dumps(partial, ensure_ascii=False, separators=(',', ':'))}"


def _collect_processing_notes(
    documents: list[dict[str, Any]],
    combined_text: str,
    chunk_count: int,
    image_notes: list[str],
    *,
    input_char_count: int | None = None,
    rag_used: bool = False,
    excerpt_fallback: bool = False,
) -> list[str]:
    notes: list[str] = []
    section_count = sum(len(doc.get("sections", [])) for doc in documents)
    table_count = sum(len(doc.get("tables", [])) for doc in documents)
    image_count = sum(len(doc.get("images", [])) for doc in documents)
    approx_chars = input_char_count if input_char_count is not None else len(combined_text)

    if excerpt_fallback:
        notes.append(
            "Vector retrieval returned little text versus document size; used a stratified excerpt "
            "(beginning, middle, end) of the full extraction for one fast pass instead of many chunk calls."
        )
    elif rag_used:
        notes.append(
            "Built summarization input from vector retrieval (RAG) over the selected document id(s); "
            "retrieved passages were capped for speed. Bracket citations [n] are still validated against "
            "the full extracted text."
        )
    if len(documents) > 1:
        notes.append(f"Combined {len(documents)} documents into one summary request.")
    if chunk_count > 1:
        notes.append(f"Used hierarchical summarization across {chunk_count} chunks for long input.")
    else:
        notes.append("Processed the source text in a single summarization pass.")

    notes.append(
        f"Processed approximately {approx_chars} characters across "
        f"{section_count} sections, {table_count} tables, and {image_count} images."
    )

    if image_notes:
        notes.append("Included image captions/descriptions when available and flagged images without textual context.")
    else:
        notes.append("No image metadata was available to influence the summary.")

    return notes


def _validate_limits(documents: list[dict[str, Any]], total_pages: int, combined_text: str) -> None:
    if len(documents) > MAX_SUMMARY_DOCUMENTS:
        raise SummarizerLimitError(
            f"You can summarize up to {MAX_SUMMARY_DOCUMENTS} documents at once."
        )
    if total_pages > MAX_SUMMARY_PAGES:
        raise SummarizerLimitError(
            f"The current summarizer supports up to {MAX_SUMMARY_PAGES} pages per request."
        )
    if len(combined_text) > MAX_SUMMARY_CHARS:
        raise SummarizerLimitError(
            f"The current summarizer supports up to {MAX_SUMMARY_CHARS} characters of extracted content per request."
        )


async def _synthesize_long_input(
    prompt_full: str,
    prompt_map: str,
    prompt_reduce: str,
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
            return await asyncio.to_thread(_call_map_chunk_prompt, prompt_map, partial_title, piece)

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
            prompt_full,
            f"{title} - final synthesis",
            reduction_chunks[0],
        )
        return final_data, len(base_chunks)

    async def _reduction(index: int, piece: str) -> dict[str, Any]:
        reduction_title = f"{title} - reduction {index}/{len(reduction_chunks)}"
        async with sem:
            return await asyncio.to_thread(_call_reduce_prompt, prompt_reduce, reduction_title, piece)

    reduction_partials = await asyncio.gather(
        *[_reduction(i, p) for i, p in enumerate(reduction_chunks, start=1)]
    )

    final_serialized = "\n\n".join(
        _serialize_partial(index, partial)
        for index, partial in enumerate(reduction_partials, start=1)
    )
    final_data = await asyncio.to_thread(
        _call_summary_prompt,
        prompt_full,
        f"{title} - final synthesis",
        final_serialized,
    )
    return final_data, len(base_chunks)


async def run_summarizer(
    doc_json: dict[str, Any] | list[dict[str, Any]],
    length: str = "medium",
    use_rag: bool | None = None,
) -> SummaryResult:
    prompt_full_tpl, prompt_map_tpl, prompt_reduce_tpl = _summarize_prompt_templates()
    prompt = prompt_full_tpl.replace("{SUMMARY_LENGTH}", _summary_length_instruction(length))

    documents = _normalize_documents(doc_json)
    image_notes: list[str] = []
    combined_text, source_documents, total_pages = _build_combined_text(documents, image_notes)
    citation_source_text = combined_text

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

    rag_used = False
    excerpt_fallback = False
    synthesis_input = combined_text
    if _should_use_rag_summarize(use_rag, len(documents), len(combined_text), total_pages):
        rag_text = await asyncio.to_thread(_retrieve_summary_context_sync, documents, combined_text)
        if len(rag_text.strip()) > 400:
            synthesis_input = rag_text
            rag_used = True
        else:
            fb_min = max(50_000, int(os.getenv("SUMMARY_FALLBACK_MIN_CHARS", "90000")))
            fb_chars = max(12_000, min(int(os.getenv("SUMMARY_FALLBACK_EXCERPT_CHARS", "52000")), 120_000))
            if len(combined_text) > fb_min:
                synthesis_input = _stratified_excerpt(combined_text, fb_chars)
                excerpt_fallback = True

    _validate_limits(documents, total_pages, synthesis_input)

    title = source_documents[0] if len(source_documents) == 1 else "Multi-document summary"
    chunk_candidates = chunk_text(
        synthesis_input,
        chunk_size=SUMMARY_CHUNK_SIZE,
        overlap=SUMMARY_CHUNK_OVERLAP,
    )

    if len(chunk_candidates) <= 1:
        data = await asyncio.to_thread(_call_summary_prompt, prompt, title, synthesis_input)
        chunk_count = 1
    else:
        data, chunk_count = await _synthesize_long_input(
            prompt,
            prompt_map_tpl,
            prompt_reduce_tpl,
            title,
            synthesis_input,
        )

    processing_notes = _collect_processing_notes(
        documents,
        combined_text,
        chunk_count,
        image_notes,
        input_char_count=len(synthesis_input),
        rag_used=rag_used,
        excerpt_fallback=excerpt_fallback,
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

    data = _normalize_summary_payload(data)
    data, ref_extras = _apply_reference_marker_postprocess(data, citation_source_text)
    if ref_extras:
        data["processing_notes"] = list(data.get("processing_notes") or []) + ref_extras

    return SummaryResult.model_validate(data)
