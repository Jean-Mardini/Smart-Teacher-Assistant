"""Resolve slide generation input: library document, pasted text, one-line prompt, or fetched URL."""

from __future__ import annotations

import asyncio
import hashlib
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from fastapi import HTTPException

from app.models.agents import QuizRequest, SlideRequest
from app.services.knowledge.indexing_pipeline import get_local_document_by_id


def inline_document_id(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:22]
    return f"inline_{digest}"


def synthetic_document_dict(document_id: str, title: str, body: str) -> dict:
    """Minimal ParsedDocument-shaped dict for ``run_slides``."""
    return {
        "document_id": document_id,
        "title": title[:500] or "Presentation",
        "metadata": {
            "filename": "inline.txt",
            "filetype": "text/plain",
            "total_pages": 1,
        },
        "sections": [
            {
                "section_id": "inline-1",
                "heading": "Source",
                "level": 1,
                "page_start": 1,
                "page_end": 1,
                "text": body,
            }
        ],
        "tables": [],
        "images": [],
    }


def _title_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc or "Web page"
        return host.replace("www.", "")[:120]
    except Exception:
        return "Web import"


def fetch_url_text(url: str, max_chars: int = 120_000) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are allowed.")

    headers = {"User-Agent": "SmartTeacherAssistant/1.0 (+local slide import)"}
    response = requests.get(url, timeout=25, headers=headers)
    response.raise_for_status()

    ctype = (response.headers.get("Content-Type") or "").lower()
    raw = response.content
    text: str

    if "html" in ctype or raw[:200].lstrip().lower().startswith(b"<!doctype") or raw[:50].lstrip().startswith(b"<"):
        charset = response.encoding or "utf-8"
        html = raw.decode(charset, errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
    else:
        text = raw.decode(response.encoding or "utf-8", errors="replace")

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError("No readable text could be extracted from the URL.")
    return text[:max_chars]


async def document_dict_for_quiz_request(req: QuizRequest) -> dict:
    """Build ParsedDocument-shaped JSON for ``run_quiz`` using the same sources as slide generation."""
    sr = SlideRequest(
        document_id=(req.document_id or "").strip() or None,
        source_text=(req.source_text or "").strip() or None,
        source_title=req.source_title,
        source_url=(req.source_url or "").strip() or None,
        n_slides=1,
        template="academic_default",
        generate_images=False,
        max_generated_images=0,
    )
    doc = await document_dict_for_slide_request(sr)
    overlay = (req.source_title or "").strip()
    if overlay:
        doc = dict(doc)
        doc["title"] = overlay[:500]
    return doc


async def document_dict_for_slide_request(req: SlideRequest) -> dict:
    """Return document JSON for ``run_slides`` from library doc, pasted/prompt text, or URL import."""
    text = (req.source_text or "").strip()
    if text:
        doc_id = inline_document_id(text)
        title = (req.source_title or "").strip() or "Presentation"
        return synthetic_document_dict(doc_id, title, text)

    url = (req.source_url or "").strip()
    if url:
        try:
            body = await asyncio.to_thread(fetch_url_text, url)
        except requests.RequestException as exc:
            raise HTTPException(status_code=400, detail=f"Could not fetch URL: {exc}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        doc_id = inline_document_id(url + "\n" + body[:4000])
        title = (req.source_title or "").strip() or _title_from_url(url)
        return synthetic_document_dict(doc_id, title, body)

    doc_id = (req.document_id or "").strip()
    if not doc_id:
        raise HTTPException(
            status_code=400,
            detail="Choose a library document, paste text, enter a prompt, or provide a URL.",
        )

    document = get_local_document_by_id(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    return document.model_dump()
