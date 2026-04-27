"""Slide generator agent implementation (owned by Angela)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

from app.models.agents import ALL_SLIDE_LAYOUT_IDS, SlideDeckResult, SlideImageAsset
from app.services.agents.slide_image_generator import attach_generated_images
from app.services.llm.groq_client import call_llm_json, truncate_text_for_slide_prompt

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "slides.md"

SLIDE_TEMPLATE_INSTRUCTIONS: dict[str, str] = {
    "academic_default": (
        "DEMO LESSON teaching deck: **concise on-slide definitions** (right card / triple cards) plus **deep speaker_notes** with **examples from the document only**. "
        "**slide_title**: bold headline (~4–10 words). "
        "**subtitle**: one framing line (**12–26 words**) — scope or definition; must not repeat the title. "
        "**bullets**: **3–5** lines; **12–28 words** each; **`**Keyword** — explanation`** with a bit more substance than a slogan when the source supports it; pull cases, numbers, or named items into the dash-clause **briefly** when present in the text. "
        "**speaker_notes**: **130–240 words** — unpack every bullet; add **why it matters**; include **concrete examples** (paraphrase or quote from the document). When the source offers multiple illustrations, use **two**; otherwise at least **one**. If no examples exist in the source, deepen with careful oral explanation **without inventing facts**. Close with a **transition** to the next slide. "
        "Set **image_refs** to the best on-document figure per slide when available; the server fills generated images when needed. "
        "Export alternates **three-card** and **image-left + bullets-right** layouts — content must read well in both. "
        "Follow Introduction → Overview → Methods → Results → Conclusion when the material supports it."
    ),
    "minimal_clean": (
        "Minimalist deck: **subtitle** on every slide; **3–5** bullets **12–22 words** (still tight — one idea per line); "
        "titles 3–7 words. Speaker notes: timing cue plus **detail and one source-grounded example** when the document includes any (**80–140 words**)."
    ),
    "workshop_interactive": (
        "Workshop session: **subtitle** + **3–5** learner-facing bullets (**12–24 words**; use *you / we* where natural); "
        "weave in **brief examples** from the source in the bullet clause where it helps. "
        "Speaker notes: **120–200 words** with activities, **1–2 document-based examples** when the text offers any, and how-to. "
        "Everything grounded in the document."
    ),
    "executive_summary": (
        "Executive deck: outcome-first **title** + **subtitle**; **3–5** takeaway bullets (**12–24 words** each). "
        "Numbers only if the source provides them. Speaker notes: **100–200 words** with decision context, **implications + source-backed examples** (cases, figures, metrics) when available."
    ),
    "deep_technical": (
        "Technical deck: precise terms from the source; **subtitle** clarifies scope; **3–5** bullets (**12–28 words**) with definitions in-line and **brief worked touches** (e.g. a value, case, or condition) when the document names one. "
        "Speaker notes: **120–220 words** with definitions, **concrete source examples** (scenarios, edge cases, numbers) and cautions — no external facts."
    ),
    "story_visual": (
        "Story-driven deck: each slide advances one beat; **subtitle** sets mood; **3–5** bullets (**12–28 words**, vivid but accurate, with **moments from the source** where possible); "
        "speaker_notes **110–200 words**: narrative detail and **examples** grounded in the document only."
    ),
}

# Shorter template blocks when SLIDE_GENERATION_FAST=1 (default) — fewer output tokens → faster Groq.
SLIDE_TEMPLATE_FAST: dict[str, str] = {
    "academic_default": (
        "Teaching deck: **slide_title** 4–8 words; **subtitle** 10–18 words (scope, not a repeat of the title). "
        "**bullets** 3–4 lines, **10–18 words** each, **Keyword** — explanation from the source only (bold the keyword). "
        "**speaker_notes** 70–110 words: mirror bullets, **one** concrete example when the text allows, short transition. "
        "**image_refs** for the best on-document figure per slide when it fits."
    ),
    "minimal_clean": (
        "Minimal deck: subtitle every slide; **3–4** bullets **10–18 words**; speaker notes **70–100 words** with one source-grounded example when possible."
    ),
    "workshop_interactive": (
        "Workshop: learner-facing bullets **10–20 words**; speaker notes **80–120 words** with one document-based activity or example."
    ),
    "executive_summary": (
        "Executive: outcome titles; **3–4** bullets **10–20 words**; speaker notes **70–110 words** with implications + one source example when available."
    ),
    "deep_technical": (
        "Technical: precise terms; **3–4** bullets **10–22 words**; speaker notes **80–120 words** with definitions and one concrete case from the text."
    ),
    "story_visual": (
        "Story deck: one beat per slide; **3–4** bullets **10–20 words**; speaker notes **75–115 words** with one grounded example and a transition."
    ),
}


def _slide_llm_fast() -> bool:
    """When on (default), use shorter template + prompt targets so Groq returns fewer tokens."""
    v = (os.getenv("SLIDE_GENERATION_FAST") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _tighten_slides_system_prompt(text: str) -> str:
    """Reduce mandated speaker-note length in slides.md (main latency driver)."""
    if not _slide_llm_fast():
        return text
    block_old = (
        "- **speaker_notes**: **130–240 words** — this is where most **detail** lives: **explain** each bullet, add **why it matters**, and include **examples**.\n"
        "  - **Examples are required when the document contains any** (case studies, scenarios, numbers, comparisons, quotes, figure takeaways): **quote or paraphrase them here** and tie them to the bullets.\n"
        "  - If the document truly has **no** illustrative material for a slide, say so briefly and deepen with **step-by-step oral reasoning** grounded only in the text (still no invented facts).\n"
        "  - Aim for **at least two distinct illustrative beats** per slide when the source supports it (e.g. one scenario + one implication), otherwise **one** solid example minimum.\n"
        "  - End with a **transition** cue to the next slide. No filler."
    )
    block_new = (
        "- **speaker_notes**: **70–120 words** — one paragraph: touch each bullet briefly, **one** concrete document example when the source has any, short **why it matters**, end with one **transition** phrase. No invented facts."
    )
    if block_old in text:
        text = text.replace(block_old, block_new)
    text = text.replace("**about 12–28 words**", "**about 10–20 words**")
    text = text.replace("**about 12–26 words**", "**about 10–20 words**")
    return text


def _format_image(img: dict[str, Any], image_notes: list[str]) -> str:
    image_id = img.get("image_id", "unknown_image")
    page = img.get("page", "?")
    caption = (img.get("caption") or "").strip()
    description = (img.get("description") or "").strip()
    asset_path = (img.get("asset_path") or img.get("path") or "").strip()

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
                "asset_path": img.get("asset_path") or img.get("path"),
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


def deck_layout_sequence(n: int, seed: str) -> list[str]:
    """Assign a non-repeating layout per slide (deterministic shuffle from seed)."""
    import random

    if n <= 0:
        return []
    r = random.Random(hash(seed) & 0xFFFFFFFF)
    pool = list(ALL_SLIDE_LAYOUT_IDS)
    out: list[str] = []
    last: str | None = None
    guard = 0
    while len(out) < n and guard < n * 50:
        guard += 1
        r.shuffle(pool)
        for layout in pool:
            if len(out) >= n:
                break
            if layout != last:
                out.append(layout)
                last = layout
            else:
                choices = [x for x in ALL_SLIDE_LAYOUT_IDS if x != last]
                pick = r.choice(choices)
                out.append(pick)
                last = pick
    while len(out) < n:
        out.append("split_text_left")
    return out[:n]


def _strip_step_prefix(line: str) -> str:
    """Remove leading ``Step 1 —`` / ``Step 2:`` labels the model may add (layouts are not step lists)."""
    s = (line or "").strip()
    if not s:
        return s
    m = re.match(r"^(step\s*\d+)(?:\s*[—\-:\.]+)?\s*(.*)$", s, re.IGNORECASE | re.DOTALL)
    if m:
        rest = (m.group(2) or "").strip()
        if rest:
            return rest
    return s


def _scannable_bullet(line: str, max_words: int = 26) -> str:
    """Turn LLM prose into a single on-slide line (one idea; a bit more room than ultra-tight)."""
    s = (line or "").strip()
    if not s:
        return s
    for sep in (". ", "? ", "! ", "; "):
        if sep in s:
            s = s.split(sep)[0].strip()
            break
    words = s.split()
    if len(words) > max_words:
        s = " ".join(words[:max_words]).rstrip(",;:") + "…"
    return s


def _coerce_layout_for_assets(layout: str, n_bullets: int) -> str:
    """Keep deck layout sequence; only fix layouts that need minimum bullet counts.

    Slide images are attached after normalization (generated or document assets), so we
    do not downgrade image-forward layouts here — export expects a large visual per slide.
    """
    if layout not in ALL_SLIDE_LAYOUT_IDS:
        layout = "split_text_left"
    if layout == "grid_quad" and n_bullets < 2:
        return "grid_triple"
    return layout


def normalize_slide(
    slide: dict[str, Any],
    fact_pool: list[str],
    slide_index: int,
    image_catalog: list[dict[str, Any]],
    forced_layout: str,
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
    while len(bullets) < 2 and fact_pool:
        candidate = fact_pool[(slide_index + pool_index) % len(fact_pool)]
        pool_index += 1
        if candidate not in bullets:
            bullets.append(candidate)

    bullets = [_scannable_bullet(_strip_step_prefix(b)) for b in bullets]
    bullets = [b for b in bullets if b]

    raw_image_refs = slide.get("image_refs") or slide.get("images") or []
    image_refs: list[str] = []
    if isinstance(raw_image_refs, list):
        for ref in raw_image_refs:
            if isinstance(ref, str) and ref in valid_image_ids and ref not in image_refs:
                image_refs.append(ref)

    if not image_refs:
        image_refs = _infer_image_refs(slide, image_catalog)

    layout = _coerce_layout_for_assets(forced_layout, len(bullets))

    raw_sub = slide.get("subtitle") or slide.get("sub_title") or slide.get("deck_subtitle")
    subtitle = (raw_sub if isinstance(raw_sub, str) else "") or ""
    subtitle = subtitle.strip()[:220]

    return {
        "slide_title": title,
        "subtitle": subtitle,
        "bullets": bullets[:5],
        "speaker_notes": slide.get("speaker_notes") or slide.get("notes") or "",
        "image_refs": image_refs[:2],
        "layout": layout,
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
    template: str = "academic_default",
    generate_images: bool = True,
    image_style: str = "educational illustration",
    max_generated_images: int = 20,
) -> SlideDeckResult:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt.replace("{N_SLIDES}", str(n_slides))
    if _slide_llm_fast():
        tmpl = SLIDE_TEMPLATE_FAST.get(template) or SLIDE_TEMPLATE_FAST["academic_default"]
    else:
        tmpl = SLIDE_TEMPLATE_INSTRUCTIONS.get(template) or SLIDE_TEMPLATE_INSTRUCTIONS["academic_default"]
    prompt = prompt.replace("{TEMPLATE_INSTRUCTIONS}", tmpl)
    prompt = _tighten_slides_system_prompt(prompt)

    title = doc_json.get("title", "Document")
    image_notes: list[str] = []
    image_catalog = _build_image_catalog(doc_json)
    full_text = build_full_text(doc_json, image_notes)
    full_text, truncated = truncate_text_for_slide_prompt(full_text)
    if truncated:
        image_notes.append(
            "Long document truncated for slide generation (Groq size limits). "
            "Set GROQ_SLIDE_SOURCE_MAX_CHARS in the environment to allow a larger excerpt."
        )

    if not full_text.strip():
        return SlideDeckResult(
            title=title,
            slides=[],
            image_catalog=[SlideImageAsset.model_validate(image) for image in image_catalog],
            image_notes=image_notes,
            processing_notes=["No textual content was extracted from the selected document."],
            template_used=template,
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

    raw = await asyncio.to_thread(call_llm_json, system, user)

    if not raw:
        return SlideDeckResult(
            title=title,
            slides=[],
            image_catalog=[SlideImageAsset.model_validate(image) for image in image_catalog],
            image_notes=image_notes,
            processing_notes=_collect_processing_notes(doc_json, image_notes),
            template_used=template,
        )

    try:
        raw_slides = raw.get("slides")
        if not isinstance(raw_slides, list):
            raw_slides = []
        slides = raw_slides[: max(n_slides, 0)]
        deck_key = str(raw.get("title", title) or title)
        layout_seq = deck_layout_sequence(max(n_slides, 1), deck_key)
        fixed_slides = [
            normalize_slide(slide, fact_pool, index, image_catalog, layout_seq[index])
            for index, slide in enumerate(slides)
        ]
        while len(fixed_slides) < n_slides:
            idx = len(fixed_slides)
            filler = {
                "slide_title": f"Slide {idx + 1}",
                "subtitle": "Supporting points from the source document — expanded in bullets and speaker notes.",
                "bullets": [],
                "speaker_notes": "",
                "image_refs": [],
            }
            fixed_slides.append(
                normalize_slide(filler, fact_pool, idx, image_catalog, layout_seq[idx])
            )
        fill_slides = bool(generate_images)
        gen_cap = max(max_generated_images, len(fixed_slides)) if fill_slides else max_generated_images
        fixed_slides, image_catalog, generation_notes = attach_generated_images(
            document_id=doc_json.get("document_id", title.lower().replace(" ", "_")),
            document_title=title,
            slides=fixed_slides,
            image_catalog=image_catalog,
            generate_images=generate_images,
            image_style=image_style,
            max_generated_images=gen_cap,
            fill_every_slide=fill_slides,
        )
        processing_notes = _collect_processing_notes(doc_json, image_notes)
        processing_notes.extend(generation_notes)

        cleaned = {
            "title": raw.get("title", title),
            "slides": fixed_slides,
            "image_catalog": image_catalog,
            "image_notes": image_notes,
            "processing_notes": processing_notes,
            "template_used": template,
        }

        return SlideDeckResult.model_validate(cleaned)

    except RuntimeError:
        raise
    except Exception as exc:
        log.warning("Slide deck validation failed: %s", exc)
        return SlideDeckResult(
            title=title,
            slides=[],
            image_catalog=[SlideImageAsset.model_validate(image) for image in image_catalog],
            image_notes=image_notes,
            processing_notes=_collect_processing_notes(doc_json, image_notes),
            template_used=template,
        )
