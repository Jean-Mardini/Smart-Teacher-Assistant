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
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

try:
    from openai import APIError, RateLimitError
except ImportError:  # pragma: no cover

    class APIError(Exception):
        """Placeholder when openai is not installed."""

    class RateLimitError(APIError):
        """Placeholder when openai is not installed."""

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


def max_slide_source_chars() -> int:
    """Upper bound on source characters sent to Groq for slide generation.

    Free / on-demand Groq tiers enforce a low **tokens-per-minute** budget; long
    documents plus the slide system prompt exceed that quickly. Override with
    ``GROQ_SLIDE_SOURCE_MAX_CHARS`` (e.g. 12000 on paid tiers).

    When ``SLIDE_GENERATION_FAST`` is on (default), the default cap is slightly higher
    (9000) because shorter speaker-note targets keep total tokens down.
    """
    raw = (os.getenv("GROQ_SLIDE_SOURCE_MAX_CHARS") or "").strip()
    if raw.isdigit():
        return max(1500, min(int(raw), 200_000))
    fast = (os.getenv("SLIDE_GENERATION_FAST") or "1").strip().lower() not in ("0", "false", "no", "off")
    return 9000 if fast else 5000


def truncate_text_for_slide_prompt(text: str) -> tuple[str, bool]:
    """Return ``(text_for_prompt, was_truncated)`` for slide LLM calls."""
    cap = max_slide_source_chars()
    t = (text or "").strip()
    if len(t) <= cap:
        return t, False
    head = t[:cap].rstrip()
    last_break = max(head.rfind("\n\n"), head.rfind(". "))
    if last_break > int(cap * 0.5):
        head = head[:last_break].rstrip()
    note = (
        "\n\n[… Excerpt ends here: document was truncated for the model size limit. "
        "Ground every slide in the text above only.]\n"
    )
    return head + note, True


def max_quiz_source_chars() -> int:
    """Cap characters from the document sent to Groq for quiz generation (TPM / context)."""
    raw = (os.getenv("GROQ_QUIZ_SOURCE_MAX_CHARS") or "").strip()
    if raw.isdigit():
        return max(2_000, min(int(raw), 200_000))
    return 18_000


def truncate_text_for_quiz_prompt(text: str) -> tuple[str, bool]:
    """Return ``(text_for_prompt, was_truncated)`` for quiz LLM calls."""
    cap = max_quiz_source_chars()
    t = (text or "").strip()
    if len(t) <= cap:
        return t, False
    head = t[:cap].rstrip()
    last_break = max(head.rfind("\n\n"), head.rfind(". "))
    if last_break > int(cap * 0.5):
        head = head[:last_break].rstrip()
    note = (
        "\n\n[… Document truncated for the quiz model limit. "
        "Write every question only from the text above.]\n"
    )
    return head + note, True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_RETRY_AFTER_HINT = re.compile(r"try again in ([\d.]+)\s*s", re.IGNORECASE)


def _groq_rate_limit_delay_seconds(exc: Exception) -> float | None:
    """Parse suggested wait from Groq / OpenAI error (JSON body, headers, or string).

    Groq TPM 429s embed ``Please try again in N.Ns`` inside ``body['error']['message']``;
    the OpenAI client's ``str(exc)`` often omits that text, so we must read ``.body``.
    """
    body = getattr(exc, "body", None)
    if isinstance(body, (bytes, bytearray)):
        try:
            body = json.loads(body.decode("utf-8", errors="replace"))
        except Exception:
            body = None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            body = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = str(err.get("message") or "")
            m = _RETRY_AFTER_HINT.search(msg)
            if m:
                return float(m.group(1))

    resp = getattr(exc, "response", None)
    if resp is not None:
        headers = getattr(resp, "headers", None) or {}
        for key in ("retry-after", "Retry-After"):
            raw = headers.get(key)
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    pass
    m = _RETRY_AFTER_HINT.search(str(exc))
    if m:
        return float(m.group(1))
    return None


def _completion_create_with_retry(**create_kwargs: Any) -> Any:
    """``chat.completions.create`` with retries on Groq 429 / TPM (on_demand tier).

    Used by plain chat (:func:`_chat`) and JSON-object completions (grading, quiz).
    Tune with ``GROQ_RATE_LIMIT_RETRIES``, ``GROQ_RATE_LIMIT_MAX_WAIT_SEC``,
    ``GROQ_RATE_LIMIT_FALLBACK_SEC``.
    """
    max_attempts = max(1, min(int(os.getenv("GROQ_RATE_LIMIT_RETRIES", "20")), 50))
    max_sleep = float(os.getenv("GROQ_RATE_LIMIT_MAX_WAIT_SEC", "120"))
    fallback = float(os.getenv("GROQ_RATE_LIMIT_FALLBACK_SEC", "2.5"))

    for attempt in range(max_attempts):
        try:
            client = _get_client()
            return client.chat.completions.create(**create_kwargs)
        except RateLimitError as exc:
            if attempt >= max_attempts - 1:
                raise
            delay = _groq_rate_limit_delay_seconds(exc)
            if delay is None:
                delay = min(max_sleep, fallback * (attempt + 1))
            else:
                delay = min(max_sleep, max(1.0, delay))
            logger.warning(
                "Groq rate limit on completion (%s/%s); sleeping %.1fs then retrying.",
                attempt + 1,
                max_attempts,
                delay,
            )
            time.sleep(delay)
        except APIError as exc:
            if getattr(exc, "status_code", None) != 429:
                raise
            if attempt >= max_attempts - 1:
                raise
            delay = _groq_rate_limit_delay_seconds(exc)
            if delay is None:
                delay = min(max_sleep, fallback * (attempt + 1))
            else:
                delay = min(max_sleep, max(1.0, delay))
            logger.warning(
                "Groq HTTP 429 on completion (%s/%s); sleeping %.1fs then retrying.",
                attempt + 1,
                max_attempts,
                delay,
            )
            time.sleep(delay)

    raise RuntimeError("_completion_create_with_retry exhausted retries")  # pragma: no cover


def _chat(system: str, user: str, temperature: float = 0.2) -> str:
    """Chat completion with retries on Groq TPM / rate limits (common on on_demand tier)."""
    response = _completion_create_with_retry(
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


def call_llm_json_object(system: str, user: str, temperature: float = 0.25) -> dict:
    """Chat completion with ``response_format=json_object`` — reliable dict root for quiz-style tasks."""
    response = _completion_create_with_retry(
        model=_get_model(),
        response_format={"type": "json_object"},
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    if not response.choices:
        raise ValueError("Empty response from Groq API.")
    content = (response.choices[0].message.content or "").strip() or "{}"
    try:
        out = json.loads(content)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        logger.warning("Groq json_object response was not valid JSON; trying brace extract")
        try:
            out = json.loads(_extract_json(content))
            return out if isinstance(out, dict) else {}
        except Exception:
            logger.warning("Quiz JSON parse failed after json_object", exc_info=True)
            return {}


def _sanitize_llm_json_payload(obj: Any) -> Any:
    """Make nested structures safe for ``json.dumps`` (finite floats, JSON-native types)."""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, int):
        return obj
    if isinstance(obj, dict):
        return {str(k): _sanitize_llm_json_payload(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_llm_json_payload(v) for v in obj]
    return str(obj)


def _grade_seed() -> int | None:
    """Optional deterministic seed for grading JSON calls (set ``GROQ_GRADE_SEED=42`` if the provider supports it)."""
    raw = (os.getenv("GROQ_GRADE_SEED") or "").strip().lower()
    if raw in ("", "none", "off"):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _grade_max_completion_tokens() -> int | None:
    """Cap completion length for grading JSON (lowers TPM; unset with 0 to disable)."""
    raw = (os.getenv("GROQ_GRADE_MAX_COMPLETION_TOKENS") or "2048").strip().lower()
    if raw in ("0", "", "none", "off"):
        return None
    try:
        v = int(float(raw))
    except ValueError:
        v = 2048
    if v <= 0:
        return None
    return max(256, min(v, 8192))


def call_llm_json_payload(
    payload: dict,
    model: Optional[str] = None,
    temperature: float = 0.15,
) -> dict:
    """Send a structured dict payload and return the JSON response as a dict.

    Uses Groq's ``json_object`` response format for reliable structured output.
    This is the entry-point used by the evaluation / grading pipeline.
    """
    chosen_model = (model or "").strip() or _get_model()
    try:
        user_content = json.dumps(_sanitize_llm_json_payload(payload), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        logger.error("Could not serialize LLM payload for Groq", exc_info=True)
        raise ValueError(f"Grading payload is not JSON-serializable: {exc}") from exc
    create_kwargs: dict[str, Any] = dict(
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
                "content": user_content,
            },
        ],
    )
    max_out = _grade_max_completion_tokens()
    if max_out is not None:
        # Groq OpenAI-compatible API accepts max_tokens for chat completions.
        create_kwargs["max_tokens"] = max_out
    seed = _grade_seed()
    if seed is not None:
        create_kwargs["seed"] = seed
    response = _completion_create_with_retry(**create_kwargs)
    if not getattr(response, "choices", None):
        raise ValueError("Empty response from Groq API (no choices).")
    content = (response.choices[0].message.content or "").strip() or "{}"
    try:
        return json.loads(content)
    except Exception:
        logger.warning("Failed to parse JSON from Groq response", exc_info=True)
        return {}
