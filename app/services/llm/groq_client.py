import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

# Load .env file
load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

if not API_KEY:
    print("WARNING: GROQ_API_KEY not found")

client = Groq(api_key=API_KEY)


def _extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output.")
    return match.group(0)


def _chat(system: str, user: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    if not response.choices:
        raise ValueError("Empty response from Groq API.")

    return response.choices[0].message.content


def call_llm_json(system: str, user: str) -> dict:
    content = _chat(system, user)

    try:
        return json.loads(_extract_json(content))
    except Exception:
        # JSON repair fallback
        repair_system = "You fix outputs to be STRICT valid JSON only."
        repair_user = (
            "Fix the following to be valid JSON ONLY.\n\n"
            f"{content}"
        )

        fixed = _chat(repair_system, repair_user)
        return json.loads(_extract_json(fixed))