"""Request / response models for the Gamma-style ``/generate-slides`` live pipeline."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class GammaSlideSpec(BaseModel):
    """One slide as returned by the LLM (before layout assignment and image paths)."""

    title: str = Field(..., min_length=1, max_length=200)
    bullets: List[str] = Field(..., min_length=1, max_length=6)
    image_prompt: str = Field(..., min_length=4, max_length=1200)
    type: str = Field(default="auto", max_length=32)

    @field_validator("bullets", mode="before")
    @classmethod
    def normalize_bullets(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            line = " ".join(item.split()).strip()
            if line and line not in out:
                out.append(line[:620])
        return out[:6]


class GenerateSlidesRequest(BaseModel):
    """Live slide JSON — same document sources as ``SlideRequest``, or raw ``document_text``."""

    document_text: Optional[str] = Field(None, max_length=120_000)
    document_id: Optional[str] = None
    source_text: Optional[str] = None
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    n_slides: int = Field(default=6, ge=3, le=20)
    deck_title: Optional[str] = Field(default=None, max_length=300)
    image_style: str = Field(default="vector_science", max_length=120)

    @model_validator(mode="after")
    def validate_source(self) -> "GenerateSlidesRequest":
        dt = (self.document_text or "").strip()
        if len(dt) >= 20:
            return self
        has_doc = bool((self.document_id or "").strip())
        has_text = bool((self.source_text or "").strip())
        has_url = bool((self.source_url or "").strip())
        if not has_doc and not has_text and not has_url:
            raise ValueError(
                "Provide document_text (at least 20 characters) or document_id, source_text, or source_url."
            )
        return self


class LiveSlideExportItem(BaseModel):
    """One slide from the live preview, for optional PPTX export."""

    title: str = "Slide"
    bullets: List[str] = Field(default_factory=list)
    layout: Optional[str] = None
    type: Optional[str] = None
    image: str = ""
    image_prompt: Optional[str] = None
    icon: Optional[str] = None
    use_icons: Optional[bool] = None


class LiveSlidesExportRequest(BaseModel):
    """Optional export: rebuild PPTX from the last live payload (images as data URLs)."""

    slides: List[LiveSlideExportItem] = Field(..., min_length=1)

    def slides_as_dicts(self) -> list[dict[str, Any]]:
        return [s.model_dump() for s in self.slides]


class LiveSlidesScreenshotExportRequest(BaseModel):
    """Export PPTX where each slide is one full-bleed PNG from the React preview (html-to-image)."""

    images: List[str] = Field(..., min_length=1, description="data:image/png;base64,... per slide")
