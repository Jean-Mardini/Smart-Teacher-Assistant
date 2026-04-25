"""Optional LaTeX-OCR for equation-like bitmaps embedded in PDFs (pix2tex / LaTeX-OCR).

Vector math in PDFs (no separate image) is not handled here — only raster/embedded images
that pix2tex can treat as a single-expression crop.

Enable with ``PDF_FORMULA_OCR=1`` (see ``.env.example``). Requires ``pip install pix2tex``;
first run may download model weights (~100MB+).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_model: Any = None
_model_failed = False
_lock = threading.Lock()


def want_formula_ocr() -> bool:
    return os.getenv("PDF_FORMULA_OCR", "0").strip().lower() in ("1", "true", "yes", "on")


def _max_images() -> int:
    try:
        return max(0, int(os.getenv("PDF_FORMULA_OCR_MAX", "25")))
    except ValueError:
        return 25


def _get_latex_ocr_model():
    global _model, _model_failed
    if _model_failed:
        return None
    if _model is None:
        try:
            from pix2tex.cli import LatexOCR

            _model = LatexOCR()
        except Exception as exc:
            logger.warning("pix2tex / LaTeX-OCR unavailable (%s). pip install pix2tex", exc)
            _model_failed = True
            return None
    return _model


def _image_dims(path: str) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def _should_try_image(w: int, h: int) -> bool:
    if w < 48 or h < 48:
        return False
    if w * h > 1_200_000:
        return False
    if max(w, h) > 1800:
        return False
    return True


def transcribe_image_file(path: str) -> str | None:
    if not path or not os.path.isfile(path):
        return None
    try:
        from PIL import Image

        pil = Image.open(path).convert("RGB")
    except Exception as exc:
        logger.debug("Formula OCR could not open %s: %s", path, exc)
        return None
    with _lock:
        model = _get_latex_ocr_model()
        if model is None:
            return None
        try:
            latex = (model(pil, resize=True) or "").strip()
            return latex or None
        except Exception as exc:
            logger.debug("Formula OCR failed for %s: %s", path, exc)
            return None


def enrich_pdf_images_with_formula_latex(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy image dicts and set ``description`` when LaTeX-OCR returns a string."""
    if not want_formula_ocr() or not images:
        return images
    max_n = _max_images()
    tried = 0
    out: list[dict[str, Any]] = []
    for img in images:
        row = dict(img)
        path = (row.get("path") or "").strip()
        dims = _image_dims(path) if path else None
        if dims and _should_try_image(*dims) and tried < max_n:
            tried += 1
            latex = transcribe_image_file(path)
            if latex:
                row["description"] = f"LaTeX (OCR): {latex}"
        out.append(row)
    return out
