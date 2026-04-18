"""Helpers for optional AI image generation for slide decks."""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any

from app.storage.files import get_generated_images_dir

DEFAULT_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
DEFAULT_IMAGE_SIZE = os.getenv("OPENAI_IMAGE_SIZE", "1536x1024")
DEFAULT_IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "medium")


def slide_image_generation_status() -> tuple[bool, str]:
    if not os.getenv("OPENAI_API_KEY"):
        return False, "Set OPENAI_API_KEY to enable AI slide image generation."

    try:
        from openai import OpenAI  # noqa: F401
    except ModuleNotFoundError:
        return False, "Install the 'openai' package in the active environment to enable AI slide image generation."

    return True, "AI slide image generation is available."


def _slugify(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "").strip("._-")
    return clean or "slide"


def _build_prompt(document_title: str, slide: dict[str, Any], image_style: str) -> str:
    bullets = "; ".join(
        bullet.strip()
        for bullet in slide.get("bullets", [])
        if isinstance(bullet, str) and bullet.strip()
    )
    speaker_notes = (slide.get("speaker_notes") or "").strip()

    prompt_lines = [
        f"Use case: {image_style}",
        "Asset type: presentation slide illustration",
        f"Primary request: create a clean, classroom-ready visual for the slide titled '{slide.get('slide_title', 'Slide')}'.",
        f"Scene/backdrop: content relevant to the document '{document_title}'.",
        f"Subject: visualize these key points accurately and simply: {bullets or slide.get('slide_title', 'slide topic')}.",
        "Style/medium: polished educational slide illustration, presentation-friendly, readable at a distance.",
        "Composition/framing: wide 16:9 composition with one clear focal subject and uncluttered background.",
        "Lighting/mood: professional, clear, informative.",
        "Color palette: balanced academic presentation colors, not overly dark.",
        "Constraints: no watermark, no logos, no UI chrome, no dense paragraphs, no small unreadable labels.",
    ]

    if speaker_notes:
        prompt_lines.append(f"Supporting details: {speaker_notes}")

    return "\n".join(prompt_lines)


def _save_generated_image(document_id: str, slide_index: int, image_bytes: bytes) -> str:
    target_dir = get_generated_images_dir() / _slugify(document_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"generated_slide_{slide_index + 1}.png"
    target_path.write_bytes(image_bytes)
    return str(target_path)


def _generate_single_image(prompt: str) -> tuple[bytes | None, str | None]:
    from openai import OpenAI

    client = OpenAI()
    response = client.images.generate(
        model=DEFAULT_IMAGE_MODEL,
        prompt=prompt,
        size=DEFAULT_IMAGE_SIZE,
        quality=DEFAULT_IMAGE_QUALITY,
        output_format="png",
        response_format="b64_json",
        n=1,
    )

    if not getattr(response, "data", None):
        return None, None

    first = response.data[0]
    payload = getattr(first, "b64_json", None)
    if not payload:
        return None, getattr(first, "revised_prompt", None)

    return base64.b64decode(payload), getattr(first, "revised_prompt", None)


def attach_generated_images(
    document_id: str,
    document_title: str,
    slides: list[dict[str, Any]],
    image_catalog: list[dict[str, Any]],
    generate_images: bool,
    image_style: str,
    max_generated_images: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    notes: list[str] = []

    if not generate_images or max_generated_images <= 0:
        return slides, image_catalog, notes

    available, status_message = slide_image_generation_status()
    if not available:
        notes.append(status_message)
        return slides, image_catalog, notes

    generated_count = 0
    updated_catalog = list(image_catalog)
    updated_slides = [dict(slide) for slide in slides]

    for slide_index, slide in enumerate(updated_slides):
        if generated_count >= max_generated_images:
            break
        if slide.get("image_refs"):
            continue

        prompt = _build_prompt(document_title, slide, image_style)
        try:
            image_bytes, revised_prompt = _generate_single_image(prompt)
        except Exception as exc:
            notes.append(f"AI image generation failed for slide {slide_index + 1}: {exc}")
            continue

        if not image_bytes:
            notes.append(f"AI image generation returned no image for slide {slide_index + 1}.")
            continue

        image_id = f"generated_slide_{slide_index + 1}"
        asset_path = _save_generated_image(document_id, slide_index, image_bytes)

        updated_catalog.append(
            {
                "image_id": image_id,
                "page": slide_index + 1,
                "caption": slide.get("slide_title", f"Slide {slide_index + 1}"),
                "description": "AI-generated slide illustration.",
                "asset_path": asset_path,
                "source": "generated",
                "prompt": revised_prompt or prompt,
            }
        )
        slide["image_refs"] = [image_id]
        generated_count += 1

    if generated_count:
        notes.append(f"Generated {generated_count} AI slide image(s) using {DEFAULT_IMAGE_MODEL}.")
    else:
        notes.append("No AI slide images were generated.")

    return updated_slides, updated_catalog, notes
