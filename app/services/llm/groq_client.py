import os
import json
import re

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()


class LLMConfigurationError(Exception):
    """Raised when Groq is not configured (missing API key or optional dependency)."""


API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

if not API_KEY:
    print("WARNING: GROQ_API_KEY not found")


def _get_client():
    if not API_KEY:
        raise LLMConfigurationError(
            "GROQ_API_KEY is not set. Add GROQ_API_KEY to a .env file in the project root "
            "(same folder as app/) or set it in your environment, then restart the API server."
        )
    try:
        from groq import Groq
    except ModuleNotFoundError as e:
        raise LLMConfigurationError(
            "The 'groq' package is not installed. Install project dependencies (e.g. pip install groq)."
        ) from e

    return Groq(api_key=API_KEY)


def _extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output.")
    return match.group(0)


def _chat(system: str, user: str, temperature: float = 0.2) -> str:
    client = _get_client()

    response = client.chat.completions.create(
        model=MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    if not response.choices:
        raise ValueError("Empty response from Groq API.")

    return response.choices[0].message.content


def call_llm_json(system: str, user: str, temperature: float = 0.2) -> dict:
    content = _chat(system, user, temperature=temperature)

    try:
        return json.loads(_extract_json(content))
    except Exception:
        # JSON repair fallback
        repair_system = "You fix outputs to be STRICT valid JSON only."
        repair_user = (
            "Fix the following to be valid JSON ONLY.\n\n"
            f"{content}"
        )

        fixed = _chat(repair_system, repair_user, temperature=0.0)
        return json.loads(_extract_json(fixed))
