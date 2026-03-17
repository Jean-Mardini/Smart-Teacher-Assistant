"""Chat-with-documents agent implementation (owned by Mark and Angela)."""

from app.services.llm.groq_client import call_llm_json
from app.services.knowledge.retrieval import Retriever


async def run_chat(question: str, retriever: Retriever):

    # ---------------------------
    # STEP 1 — Retrieve chunks
    # ---------------------------
    chunks = retriever.retrieve(question, top_k=3)

    if not chunks:
        return {"answer": "Not found in document"}

    # ---------------------------
    # STEP 2 — Build context
    # ---------------------------
    context_chunks = [
        getattr(c, "chunk_text", "") for c in chunks
    ]

    context = "\n\n".join(context_chunks)

    # ---------------------------
    # STEP 3 — Prompt
    # ---------------------------
    system_prompt = """
You are an AI teaching assistant.
Answer ONLY using the provided document context.
If the answer is not in the context, say: "Not found in document".
"""

    user_prompt = f"""
DOCUMENT CONTEXT:
{context}

QUESTION:
{question}

Return JSON:
{{
  "answer": "string"
}}
"""

    # ---------------------------
    # STEP 4 — Call LLM
    # ---------------------------
    try:
        response = await call_llm_json(
            system=system_prompt,
            user=user_prompt
        )

        # Safety: ensure correct format
        if "answer" not in response:
            return {"answer": "Error: invalid response format"}

        return response

    except Exception as e:
        print("LLM error:", e)
        return {"answer": "Error generating response"}