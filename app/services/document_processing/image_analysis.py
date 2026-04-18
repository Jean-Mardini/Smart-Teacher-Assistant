"""Helpers for extracting useful text from document images."""

"""angelas part"""

from __future__ import annotations

from io import BytesIO


def _load_ocr_modules():
    try:
        from PIL import Image, ImageOps
    except ModuleNotFoundError:
        return None, None, None

    try:
        import pytesseract
    except ModuleNotFoundError:
        return None, None, None

    return Image, ImageOps, pytesseract


def analyze_pil_image(image) -> str | None:
    """Return OCR text from a PIL image when optional OCR dependencies are available."""
    modules = _load_ocr_modules()
    if modules == (None, None, None):
        return None

    _, ImageOps, pytesseract = modules

    try:
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)
        text = pytesseract.image_to_string(image)
    except Exception:
        return None

    cleaned = " ".join((text or "").split())
    return cleaned or None


def analyze_image_bytes(image_bytes: bytes) -> str | None:
    """Return OCR text when optional OCR dependencies are available."""
    if not image_bytes:
        return None

    modules = _load_ocr_modules()
    if modules == (None, None, None):
        return None

    Image, _, _ = modules

    try:
        image = Image.open(BytesIO(image_bytes))
    except Exception:
        return None

    return analyze_pil_image(image)
