"""Slide generator agent implementation (owned by Angela)."""

"""angelas part"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.models.agents import SlideDeckResult, SlideImageAsset
from app.services.agents.slide_image_generator import attach_generated_images
from app.services.llm.groq_client import call_llm_json

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "slides.md"


def _format_image(img: dict[str, Any], image_notes: list[str]) -> str:
    image_id = img.get("image_id", "unknown_image")
    page = img.get("page", "?")
    caption = (img.get("caption") or "").strip()
    description = (img.get("description") or "").strip()
    asset_path = (img.get("asset_path") or "").strip()

    if not caption and not description and not asset_path:
        image_notes.append(
            f"Image on page {page} had no caption or description, so it could not be turned into slide content reliably."
        )
        return ""

    parts = [f"Important image [{image_id}] (page {page})"]
    if caption:
        parts.append(f"Caption: {caption}")
    if description:
        parts.append(f"Description: {description}")
    elif asset_path:
        parts.append("Description: Visual asset extracted, but no OCR text was available.")
    if asset_path:
        parts.append("Export note: the original image asset is available for PPTX export.")
    return "\n".join(parts)


def _build_image_catalog(document_json: dict[str, Any]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []

    for img in document_json.get("images", []):
        image_id = img.get("image_id")
        if not image_id:
            continue

        catalog.append(
            {
                "image_id": image_id,
                "page": img.get("page", 1),
                "caption": img.get("caption"),
                "description": img.get("description"),
                "asset_path": img.get("asset_path"),
            }
        )

    return catalog


def build_full_text(document_json: dict[str, Any], image_notes: list[str] | None = None) -> str:
    parts: list[str] = []
    image_notes = image_notes if image_notes is not None else []

    for s in document_json.get("sections", []):
        parts.append(f"{s.get('heading', '')}\n{s.get('text', '')}".strip())

    for t in document_json.get("tables", []):
        parts.append(f"Table: {t.get('caption', '')}\n{t.get('text', '')}".strip())

    for img in document_json.get("images", []):
        formatted = _format_image(img, image_notes)
        if formatted:
            parts.append(formatted)

    return "\n\n".join(part for part in parts if part.strip())


def extract_fact_pool(full_text: str) -> list[str]:
    raw_parts = re.split(r"[\n\.]+", full_text)
    facts: list[str] = []

    for part in raw_parts:
        clean = part.strip(" -:\t")
        if len(clean) < 12:
            continue

        subparts = re.split(r",| and | with ", clean)
        for subpart in subparts:
            fact = subpart.strip(" -:\t")
            if len(fact) >= 12 and fact not in facts:
                facts.append(fact)

    return facts


def _infer_image_refs(slide: dict[str, Any], image_catalog: list[dict[str, Any]]) -> list[str]:
    if not image_catalog:
        return []

    combined_text = " ".join(
        [
            slide.get("slide_title") or slide.get("title") or "",
            *(bullet for bullet in (slide.get("bullets") or slide.get("points") or []) if isinstance(bullet, str)),
            slide.get("speaker_notes") or slide.get("notes") or "",
        ]
    ).lower()

    inferred: list[str] = []
    for image in image_catalog:
        image_id = image.get("image_id")
        caption = (image.get("caption") or "").strip().lower()
        if not image_id:
            continue
        if image_id.lower() in combined_text:
            inferred.append(image_id)
            continue
        if caption and len(caption) > 6 and caption in combined_text:
            inferred.append(image_id)

    if inferred:
        return inferred[:2]

    if any(token in combined_text for token in ("image", "figure", "diagram", "chart")) and len(image_catalog) == 1:
        return [image_catalog[0]["image_id"]]

    return []


def normalize_slide(
    slide: dict[str, Any],
    fact_pool: list[str],
    slide_index: int,
    image_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    title = slide.get("slide_title") or slide.get("title") or f"Slide {slide_index + 1}"
    raw_bullets = slide.get("bullets") or slide.get("points") or []
    valid_image_ids = {image.get("image_id") for image in image_catalog if image.get("image_id")}

    bullets: list[str] = []
    for bullet in raw_bullets:
        if not isinstance(bullet, str):
            continue

        pieces = re.split(r"[\n]+|; ", bullet)
        for piece in pieces:
            clean = piece.strip(" -\t")
            if clean and clean not in bullets:
                bullets.append(clean)

    pool_index = 0
    while len(bullets) < 3 and fact_pool:
        candidate = fact_pool[(slide_index + pool_index) % len(fact_pool)]
        pool_index += 1
        if candidate not in bullets:
            bullets.append(candidate)

    raw_image_refs = slide.get("image_refs") or slide.get("images") or []
    image_refs: list[str] = []
    if isinstance(raw_image_refs, list):
        for ref in raw_image_refs:
            if isinstance(ref, str) and ref in valid_image_ids and ref not in image_refs:
                image_refs.append(ref)

    if not image_refs:
        image_refs = _infer_image_refs(slide, image_catalog)

    return {
        "slide_title": title,
        "bullets": bullets[:5],
        "speaker_notes": slide.get("speaker_notes") or slide.get("notes") or "",
        "image_refs": image_refs[:2],
    }


def _collect_processing_notes(document_json: dict[str, Any], image_notes: list[str]) -> list[str]:
    section_count = len(document_json.get("sections", []))
    table_count = len(document_json.get("tables", []))
    image_count = len(document_json.get("images", []))
    notes = [
        f"Built slides from {section_count} sections, {table_count} tables, and {image_count} images."
    ]

    if image_notes:
        notes.append("Included image captions/descriptions when available and flagged images without textual context.")
    else:
        notes.append("No document image metadata was available to influence the slide deck.")

    return notes


async def run_slides(
    doc_json: dict[str, Any],
    n_slides: int,
    generate_images: bool = False,
    image_style: str = "educational illustration",
    max_generated_images: int = 3,
) -> SlideDeckResult:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt.replace("{N_SLIDES}", str(n_slides))

    title = doc_json.get("title", "Document")
    image_notes: list[str] = []
    image_catalog = _build_image_catalog(doc_json)
    full_text = build_full_text(doc_json, image_notes)

    if not full_text.strip():
        return SlideDeckResult(
            title=title,
            slides=[],
            image_catalog=[SlideImageAsset.model_validate(image) for image in image_catalog],
            image_notes=image_notes,
            processing_notes=["No textual content was extracted from the selected document."],
        )

    fact_pool = extract_fact_pool(full_text)

    system = "Return ONLY valid JSON. No explanations."
    user = f"""
{prompt}

TITLE:
{title}

TEXT:
{full_text}
"""

    raw = call_llm_json(system, user)

    print("RAW AFTER PARSE:", raw)

    if not raw:
        return SlideDeckResult(
            title=title,
            slides=[],
            image_catalog=[SlideImageAsset.model_validate(image) for image in image_catalog],
            image_notes=image_notes,
            processing_notes=_collect_processing_notes(doc_json, image_notes),
        )

    try:
        slides = raw.get("slides", [])
        fixed_slides = [
            normalize_slide(slide, fact_pool, index, image_catalog)
            for index, slide in enumerate(slides)
        ]
        fixed_slides, image_catalog, generation_notes = attach_generated_images(
            document_id=doc_json.get("document_id", title.lower().replace(" ", "_")),
            document_title=title,
            slides=fixed_slides,
            image_catalog=image_catalog,
            generate_images=generate_images,
            image_style=image_style,
            max_generated_images=max_generated_images,
        )
        processing_notes = _collect_processing_notes(doc_json, image_notes)
        processing_notes.extend(generation_notes)

        cleaned = {
            "title": raw.get("title", title),
            "slides": fixed_slides,
            "image_catalog": image_catalog,
            "image_notes": image_notes,
            "processing_notes": processing_notes,
        }

        return SlideDeckResult.model_validate(cleaned)

    except Exception as exc:
        print("VALIDATION ERROR:", exc)
        return SlideDeckResult(
            title=title,
            slides=[],
            image_catalog=[SlideImageAsset.model_validate(image) for image in image_catalog],
            image_notes=image_notes,
            processing_notes=_collect_processing_notes(doc_json, image_notes),
        )
