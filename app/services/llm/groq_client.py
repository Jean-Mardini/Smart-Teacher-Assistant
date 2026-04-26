"""Unified Groq LLM client (OpenAI-compatible endpoint).

Shared by every feature: evaluation, summarisation, quiz, slides, chat.
Two caches keep this fast:
  - Config cache: reads config.json only when the file's mtime changes.
  - Client cache: reuses the same OpenAI client until the API key changes.
Call ``invalidate_config_cache()`` after writing config.json so the next
request picks up the new key immediately.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama-3.3-70b-versatile"


class LLMConfigurationError(Exception):
    """Raised when the Groq API key is missing or openai package is absent."""


# ---------------------------------------------------------------------------
# Config-file cache
# ---------------------------------------------------------------------------

_config_cache: dict = {}
_config_mtime: float = -1.0


def _saved_config_path() -> Optional[Path]:
    try:
        from app.storage.files import get_evaluation_dir
        return get_evaluation_dir() / "config.json"
    except Exception:
        logger.debug("Could not resolve config path", exc_info=True)
        return None


def _load_saved_config() -> dict:
    global _config_cache, _config_mtime
    path = _saved_config_path()
    if path is None or not path.exists():
        return {}
    try:
        mtime = path.stat().st_mtime
        if mtime == _config_mtime and _config_cache:
            return _config_cache
        data = json.loads(path.read_text(encoding="utf-8"))
        _config_cache = data if isinstance(data, dict) else {}
        _config_mtime = mtime
        logger.debug("Groq config reloaded from disk")
        return _config_cache
    except Exception:
        logger.warning("Failed to load Groq config from disk", exc_info=True)
        return {}


def invalidate_config_cache() -> None:
    """Call immediately after writing config.json."""
    global _config_cache, _config_mtime
    _config_cache = {}
    _config_mtime = -1.0
    # Also reset the cached client so a new key takes effect at once.
    global _client, _client_key
    _client = None
    _client_key = ""


# ---------------------------------------------------------------------------
# Client cache
# ---------------------------------------------------------------------------

_client = None
_client_key: str = ""


def _get_api_key() -> str:
    env = (os.getenv("GROQ_API_KEY") or "").strip()
    return env or str(_load_saved_config().get("GROQ_API_KEY", "")).strip()


def _get_model() -> str:
    env = (os.getenv("GROQ_MODEL") or "").strip()
    if env:
        return env
    return str(_load_saved_config().get("GROQ_MODEL", "")).strip() or DEFAULT_MODEL


def _get_client():
    global _client, _client_key
    api_key = _get_api_key()
    if not api_key:
        raise LLMConfigurationError(
            "GROQ_API_KEY is not configured. "
            "Paste your key in the AI Key panel in the sidebar, "
            "or set GROQ_API_KEY in a .env file."
        )
    if _client is None or _client_key != api_key:
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise LLMConfigurationError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from exc
        _client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        _client_key = api_key
        logger.debug("Groq client initialised (model=%s)", _get_model())
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output.")
    return match.group(0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _chat(system: str, user: str, temperature: float = 0.2) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=_get_model(),
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    if not response.choices:
        raise ValueError("Empty response from Groq API.")
    return response.choices[0].message.content or ""


def call_llm_json(system: str, user: str, temperature: float = 0.2) -> dict:
    """Send a plain chat prompt; parse and return the response as a dict."""
    content = _chat(system, user, temperature=temperature)
    try:
        return json.loads(_extract_json(content))
    except Exception:
        repair_system = "You fix outputs to be STRICT valid JSON only."
        repair_user = f"Fix the following to be valid JSON ONLY.\n\n{content}"
        fixed = _chat(repair_system, repair_user, temperature=0.0)
        return json.loads(_extract_json(fixed))


def call_llm_json_payload(
    payload: dict,
    model: Optional[str] = None,
    temperature: float = 0.15,
) -> dict:
    """Send a structured dict payload and return the JSON response as a dict.

    Uses Groq's ``json_object`` response format for reliable structured output.
    This is the entry-point used by the evaluation / grading pipeline.
    """
    client = _get_client()
    chosen_model = (model or "").strip() or _get_model()
    response = client.chat.completions.create(
        model=chosen_model,
        response_format={"type": "json_object"},
        temperature=temperature,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an academic grading assistant. "
                    "Return valid JSON only, no markdown."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ],
    )
    content = response.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except Exception:
        logger.warning("Failed to parse JSON from Groq response", exc_info=True)
        return {}
