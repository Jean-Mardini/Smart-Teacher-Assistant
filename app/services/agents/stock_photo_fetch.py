"""Optional Pexels / Unsplash stock photos for slide imagery when AI providers fail or mix modes."""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

log = logging.getLogger(__name__)


def stock_photo_apis_configured() -> bool:
    """True when at least one stock API key is present (see ``.env.example``)."""
    import os

    pex = (os.getenv("PEXELS_API_KEY") or "").strip()
    uns = (os.getenv("UNSPLASH_ACCESS_KEY") or "").strip()
    return bool(pex or uns)


def _search_query(slide: dict[str, Any], document_title: str, slide_index: int) -> str:
    title = (slide.get("title") or slide.get("slide_title") or "").strip()
    bullets = slide.get("bullets") or []
    bits = [title]
    for b in bullets[:2]:
        if isinstance(b, str) and b.strip():
            bits.append(re.sub(r"\*\*([^*]+)\*\*", r"\1", b)[:120])
    q = " ".join(bits).strip()
    if len(q) < 6:
        q = (document_title or "education science learning").strip()
    q = re.sub(r"\s+", " ", q)
    # Stock APIs prefer short topical queries
    return q[:90] if len(q) > 90 else q


def _pexels_fetch(query: str, slide_index: int) -> tuple[bytes | None, str | None]:
    import os

    key = (os.getenv("PEXELS_API_KEY") or "").strip()
    if not key:
        return None, None
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": key},
            params={"query": query, "per_page": 3, "orientation": "landscape"},
            timeout=22,
        )
        if r.status_code != 200:
            log.debug("Pexels HTTP %s", r.status_code)
            return None, None
        data = r.json()
        photos = data.get("photos") or []
        if not photos:
            return None, None
        p = photos[abs(slide_index) % len(photos)]
        src = (p.get("src") or {}).get("large2x") or (p.get("src") or {}).get("large")
        if not src:
            return None, None
        ir = requests.get(src, timeout=35)
        if ir.status_code == 200 and ir.content and len(ir.content) > 2000:
            return ir.content, "pexels"
    except Exception as exc:
        log.debug("Pexels fetch failed: %s", exc)
    return None, None


def _unsplash_fetch(query: str, slide_index: int) -> tuple[bytes | None, str | None]:
    import os

    key = (os.getenv("UNSPLASH_ACCESS_KEY") or "").strip()
    if not key:
        return None, None
    try:
        r = requests.get(
            "https://api.unsplash.com/search/photos",
            headers={"Authorization": f"Client-ID {key}"},
            params={"query": query, "per_page": 3, "orientation": "landscape"},
            timeout=22,
        )
        if r.status_code != 200:
            log.debug("Unsplash HTTP %s", r.status_code)
            return None, None
        data = r.json()
        results = data.get("results") or []
        if not results:
            return None, None
        item = results[abs(slide_index) % len(results)]
        src = (item.get("urls") or {}).get("regular") or (item.get("urls") or {}).get("full")
        if not src:
            return None, None
        ir = requests.get(
            src,
            timeout=35,
            headers={"User-Agent": "SmartTeacherAssistant/1.0 (stock fallback)"},
        )
        if ir.status_code == 200 and ir.content and len(ir.content) > 2000:
            return ir.content, "unsplash"
    except Exception as exc:
        log.debug("Unsplash fetch failed: %s", exc)
    return None, None


def fetch_stock_photo_bytes(
    slide: dict[str, Any],
    document_title: str,
    slide_index: int,
) -> tuple[bytes | None, str | None]:
    """
    Download a landscape stock image if Pexels and/or Unsplash keys are set.

    Returns ``(raw_bytes, "pexels"|"unsplash")`` or ``(None, None)`` on miss.
    """
    if not stock_photo_apis_configured():
        return None, None
    q = _search_query(slide, document_title, slide_index)
    if not q:
        return None, None
    raw, src = _pexels_fetch(q, slide_index)
    if raw:
        return raw, src
    return _unsplash_fetch(q, slide_index)
