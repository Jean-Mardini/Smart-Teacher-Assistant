"""Chat-with-documents agent implementation (owned by Mark and Angela)."""

from __future__ import annotations

from typing import Any

from app.services.llm.groq_client import call_llm_json


def _build_source_entry(chunk: Any) -> dict[str, str]:
    metadata = getattr(chunk, "metadata", {}) or {}
    return {
        "document_title": getattr(chunk, "document_title", "Document"),
        "section_heading": getattr(chunk, "section_heading", None),
        "source_type": metadata.get("source_type", "section"),
        "page": metadata.get("page") or metadata.get("page_start"),
    }


async def run_chat(
    question: str,
    retriever: Any,
    length: str = "medium",
    top_k: int = 3,
    temperature: float = 0.2,
    document_ids: list[str] | None = None,
):
    chunks = retriever.retrieve(question, top_k=top_k)

    if document_ids:
        allowed = set(document_ids)
        chunks = [chunk for chunk in chunks if getattr(chunk, "document_id", None) in allowed]

    if not chunks:
        return {
            "answer": "Not found in document",
            "sources": [],
            "processing_notes": ["No relevant indexed chunks were found for the selected question."],
        }

    context_chunks = []
    sources = []
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", {}) or {}
        source_type = metadata.get("source_type", "section")
        source_label = (
            f"[{getattr(chunk, 'document_title', 'Document')} | "
            f"{source_type} | "
            f"{getattr(chunk, 'section_heading', 'Context')}]"
        )
        context_chunks.append(f"{source_label}\n{getattr(chunk, 'chunk_text', '')}")
        sources.append(_build_source_entry(chunk))

    context = "\n\n".join(context_chunks)

    length_guidance = {
        "short": "Answer in 1-2 concise sentences, about 15 to 35 words.",
        "medium": (
            "Answer in a clearly developed paragraph of about 60 to 100 words. "
            "Include the main idea and the most important supporting details from the context."
        ),
        "long": (
            "Answer in a detailed response of about 120 to 180 words. "
            "Include the main idea, supporting points, and relevant details from the context."
        ),
    }

    system_prompt = """
You are an AI teaching assistant.
Answer ONLY using the provided document context.
The context can include sections, tables, and image descriptions/captions.
If the answer is not in the context, say: "Not found in document".
Return strict JSON only.
"""

    user_prompt = f"""
DOCUMENT CONTEXT:
{context}

QUESTION:
{question}

RESPONSE LENGTH:
{length_guidance.get(length, "Answer in a short paragraph.")}

Return JSON:
{{
  "answer": "string"
}}
"""

    try:
        response = call_llm_json(
            system=system_prompt,
            user=user_prompt,
            temperature=temperature,
        )

        if not isinstance(response, dict) or "answer" not in response:
            return {
                "answer": "Error: invalid response format",
                "sources": sources,
                "processing_notes": ["The model response did not match the expected JSON shape."],
            }

        return {
            "answer": response["answer"],
            "sources": sources,
            "processing_notes": [
                f"Retrieved {len(chunks)} chunks with top_k={top_k}.",
                f"Used model temperature={temperature}.",
                "Context may include sections, tables, and image descriptions when they were indexed.",
            ],
        }

    except Exception as e:
        print("LLM error:", e)
        return {
            "answer": "Error generating response",
            "sources": sources,
            "processing_notes": [f"LLM error: {e}"],
        }
