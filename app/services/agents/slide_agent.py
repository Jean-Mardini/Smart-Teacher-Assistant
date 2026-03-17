
"""Slide generator agent implementation (owned by Angela)."""
from pathlib import Path
from app.services.llm.groq_client import call_llm_json
from app.models.agents import SlideDeckResult

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "slides.md"


def build_full_text(document_json):
    parts = []

    sections = document_json.get("sections", [])
    for s in sections:
        heading = s.get("heading", "")
        content = s.get("text", "")   # FIXED
        parts.append(f"{heading}\n{content}")

    tables = document_json.get("tables", [])
    for t in tables:
        caption = t.get("caption", "")
        text = t.get("text", "")
        parts.append(f"Table: {caption}\n{text}")

    images = document_json.get("images", [])
    for img in images:
        caption = img.get("caption", "")
        desc = img.get("description", "")
        parts.append(f"Image: {caption}\n{desc}")

    return "\n\n".join(parts)


async def run_slides(doc_json, n_slides: int = 6) -> SlideDeckResult:
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt.replace("{N_SLIDES}", str(n_slides))

    title = doc_json.get("title", "Document")  # FIXED
    full_text = build_full_text(doc_json)

    system = "You output strict JSON only."

    user = f"""
{prompt}

TITLE:
{title}

TEXT:
{full_text}
"""

    data = call_llm_json(system, user)

    return SlideDeckResult.model_validate(data)

"""Slide generator agent implementation (owned by Angela)."""



