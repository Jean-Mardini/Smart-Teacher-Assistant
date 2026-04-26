"""Live Gamma-style slide generation: Groq JSON + layouts + images → JSON for React (optional PPTX export)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Response

from app.models.agents import SlideRequest
from app.models.modern_slide_generation import (
    GenerateSlidesRequest,
    LiveSlidesExportRequest,
    LiveSlidesScreenshotExportRequest,
)
from app.services.agents.image_slide_pptx_export import build_pptx_full_bleed_images
from app.services.agents.modern_gamma_slide_system import run_live_slides_json
from app.services.agents.slide_html_playwright_export import build_pptx_live_auto
from app.services.agents.slide_image_generator import assert_live_slide_deck_payload
from app.services.agents.slide_agent import build_full_text
from app.services.agents.slide_input import document_dict_for_slide_request

router = APIRouter(tags=["generate-slides"])


async def _resolve_document_for_live(req: GenerateSlidesRequest) -> tuple[str, str]:
    """Return (text, title) for the LLM from raw text or the same sources as library slides."""
    raw = (req.document_text or "").strip()
    if len(raw) >= 20:
        title = (req.deck_title or "").strip() or "Presentation"
        return raw[:120_000], title

    sr = SlideRequest(
        document_id=(req.document_id or "").strip() or None,
        source_text=(req.source_text or "").strip() or None,
        source_title=req.source_title,
        source_url=(req.source_url or "").strip() or None,
        n_slides=req.n_slides,
        template="academic_default",
        generate_images=False,
        max_generated_images=0,
    )
    doc = await document_dict_for_slide_request(sr)
    text = build_full_text(doc).strip()
    if len(text) < 20:
        raise HTTPException(
            status_code=400,
            detail="Not enough text from the selected source (need at least 20 characters).",
        )
    title = (req.deck_title or "").strip() or (doc.get("title") or "Presentation")
    return text[:120_000], title


@router.post("/generate-slides")
async def generate_slides(req: GenerateSlidesRequest):
    """Return structured slides with layouts and PNG data URLs for instant React rendering (no PPTX)."""
    text, deck_title = await _resolve_document_for_live(req)
    try:
        # Await full pipeline (Groq + every slide image); same semantics as awaiting Promise.all on the server.
        return await asyncio.to_thread(
            run_live_slides_json,
            text,
            req.n_slides,
            deck_title,
            req.image_style.strip() or "vector_science",
            req.presentation_detail,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Slide generation failed: {exc}") from exc


@router.post("/generate-slides/export-pptx")
async def export_live_slides_pptx(body: LiveSlidesExportRequest):
    """Export deck to PPTX: HTML/CSS → Playwright PNG per slide (Gamma-style), fallback to python-pptx."""
    slides_dicts = body.slides_as_dicts()
    assert_live_slide_deck_payload(slides_dicts)
    try:
        pptx_bytes, _mode = await asyncio.to_thread(build_pptx_live_auto, slides_dicts)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PPTX export failed: {exc}") from exc

    headers = {"Content-Disposition": 'attachment; filename="slides_live_export.pptx"'}
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers=headers,
    )


@router.post("/generate-slides/export-pptx-screenshots")
async def export_live_slides_screenshots(body: LiveSlidesScreenshotExportRequest):
    """Gamma-style export: each slide is one full-bleed image (matches React UI pixel-for-pixel)."""
    try:
        pptx_bytes = build_pptx_full_bleed_images(body.images)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PPTX screenshot export failed: {exc}") from exc

    headers = {"Content-Disposition": 'attachment; filename="slides_preview_export.pptx"'}
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers=headers,
    )
