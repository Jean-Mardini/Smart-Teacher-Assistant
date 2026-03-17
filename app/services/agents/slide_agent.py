"""Slide generator agent implementation (owned by Angela)."""

from pathlib import Path
from app.services.llm.groq_client import call_llm_json
from app.models.agents import SlideDeckResult

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "slides.md"


def build_full_text(document_json: dict) -> str:
    parts = []

    # Sections
    for s in document_json.get("sections", []):
        parts.append(f"{s.get('heading','')}\n{s.get('text','')}")

    # Tables
    for t in document_json.get("tables", []):
        parts.append(f"Table: {t.get('caption','')}\n{t.get('text','')}")

    # Images
    for img in document_json.get("images", []):
        parts.append(f"Image: {img.get('caption','')}\n{img.get('description','')}")

    return "\n\n".join(parts)


async def run_slides(doc_json: dict, n_slides: int) -> SlideDeckResult:

    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt.replace("{N_SLIDES}", str(n_slides))

    title = doc_json.get("title", "Document")
    full_text = build_full_text(doc_json)

    # Safety check
    if not full_text.strip():
        return SlideDeckResult(title=title, slides=[])

    system = "Return ONLY valid JSON. No explanations."

    user = f"""
{prompt}

TITLE:
{title}

TEXT:
{full_text}
"""

    # 🔥 CALL LLM (SYNC → NO await)
    raw = call_llm_json(system, user)

    print("🔥 RAW AFTER PARSE:", raw)

    if not raw:
        return SlideDeckResult(title=title, slides=[])

    try:
        slides = raw.get("slides", [])

        fixed_slides = []

        for s in slides:
            fixed_slides.append({
                "slide_title": s.get("slide_title") or s.get("title") or "Untitled",
                "bullets": s.get("bullets") or s.get("points") or [],
                "speaker_notes": s.get("speaker_notes") or s.get("notes") or ""
            })

        cleaned = {
            "title": raw.get("title", title),
            "slides": fixed_slides
        }

        return SlideDeckResult.model_validate(cleaned)

    except Exception as e:
        print("❌ VALIDATION ERROR:", e)
        return SlideDeckResult(title=title, slides=[])