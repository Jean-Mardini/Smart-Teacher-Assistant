from pathlib import Path
from app.services.llm.groq_client import call_llm_json
from app.models.agents import SummaryResult

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "summarize.md"


def build_full_text(document_json):
    sections = document_json.get("sections", [])

    parts = []
    for s in sections:
        heading = s.get("heading", "")
        content = s.get("text", "")
        parts.append(f"{heading}\n{content}")

    return "\n\n".join(parts)


async def run_summarizer(doc_json, length: str = "medium") -> SummaryResult:

    prompt = PROMPT_PATH.read_text(encoding="utf-8")

    length_map = {
        "short": "maximum 80 words",
        "medium": "maximum 150 words",
        "long": "maximum 250 words"
    }

    summary_length = length_map.get(length, "maximum 150 words")

    prompt = prompt.replace("{SUMMARY_LENGTH}", summary_length)

    title = doc_json.get("title", "Document")

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

    return SummaryResult.model_validate(data)