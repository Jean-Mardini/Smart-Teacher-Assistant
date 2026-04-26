"""Helpers for optional slide images: Hugging Face, xAI, OpenAI, or local placeholders (demo / no API)."""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import logging
import os
import re
import textwrap
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import requests

from app.services.agents.stock_photo_fetch import fetch_stock_photo_bytes, stock_photo_apis_configured
from app.storage.files import get_generated_images_dir

# OpenAI image defaults (when SLIDE_IMAGE_PROVIDER=openai or only OPENAI_API_KEY is set)
DEFAULT_OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
DEFAULT_OPENAI_IMAGE_SIZE = os.getenv("OPENAI_IMAGE_SIZE", "1536x1024")
DEFAULT_OPENAI_IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "medium")

# xAI Grok Imagine (OpenAI-compatible client)
DEFAULT_XAI_IMAGE_MODEL = os.getenv("XAI_IMAGE_MODEL", "grok-imagine-image")
DEFAULT_XAI_API_BASE = os.getenv("XAI_API_BASE", "https://api.x.ai/v1").rstrip("/")

# Hugging Face Inference — default to a widely available diffusion model (override with HF_IMAGE_MODEL).
DEFAULT_HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "stabilityai/sdxl-turbo")

# Classic Inference API models used as REST fallbacks when InferenceClient returns nothing.
_HF_REST_FALLBACK_MODELS = (
    "stabilityai/sdxl-turbo",
    "stabilityai/stable-diffusion-2",
)


def _hf_token() -> str | None:
    return (os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or "").strip() or None


def _env_flag(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def _hf_only_enabled() -> bool:
    """Opt-in: when True, try Hugging Face **first**, then optional stock / backup AI (see SLIDE_IMAGE_FALLBACK_AFTER_HF).

    Default False — legacy behavior: placeholder if no keys; HF / xAI / OpenAI when configured (no extra APIs required).
    """
    raw = (os.getenv("SLIDE_IMAGE_HF_ONLY") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _hf_fallback_after_hf_failure_enabled() -> bool:
    """After HF retries exhaust (SLIDE_IMAGE_HF_ONLY=1): try Pexels/Unsplash, then xAI/OpenAI."""
    raw = (os.getenv("SLIDE_IMAGE_FALLBACK_AFTER_HF") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _hf_retries_per_slide() -> int:
    try:
        return max(1, min(12, int((os.getenv("SLIDE_IMAGE_HF_RETRIES_PER_SLIDE") or "1").strip() or "1")))
    except ValueError:
        return 1


def slide_image_parallel_workers() -> int:
    """Threads for parallel slide images (live JSON, PPTX prep, teacher-deck attachment). Env: SLIDE_IMAGE_PARALLEL."""
    try:
        return max(1, min(8, int((os.getenv("SLIDE_IMAGE_PARALLEL") or "8").strip() or "8")))
    except ValueError:
        return 8


def pillow_can_draw_slide_placeholders() -> bool:
    """Local PNG previews require Pillow."""
    try:
        from PIL import Image  # noqa: F401

        return True
    except ModuleNotFoundError:
        return False


def get_slide_image_provider() -> Literal["huggingface", "openai", "xai", "placeholder"] | None:
    """Which backend generates slide images.

    ``SLIDE_IMAGE_PROVIDER`` overrides: ``huggingface`` | ``hf`` | ``xai`` | ``openai`` | ``placeholder`` | ``demo``.
    Otherwise: same cloud order as before; if **no** cloud keys are set and
    ``SLIDE_IMAGE_NOAPI_PLACEHOLDERS`` is not disabled (default: on), returns ``placeholder``.
    """
    if _hf_only_enabled() and _hf_token():
        return "huggingface"

    explicit = (os.getenv("SLIDE_IMAGE_PROVIDER") or "").strip().lower()
    if explicit in ("placeholder", "demo", "local"):
        return "placeholder"
    if explicit in ("huggingface", "hf"):
        return "huggingface"
    if explicit in ("openai", "xai"):
        return explicit  # type: ignore[return-value]
    if _hf_token():
        return "huggingface"
    if os.getenv("XAI_API_KEY"):
        return "xai"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if _env_flag("SLIDE_IMAGE_NOAPI_PLACEHOLDERS", True):
        return "placeholder"
    return None


def active_image_model_label() -> str:
    p = get_slide_image_provider()
    if p == "placeholder":
        return "local_placeholder"
    if p == "huggingface":
        return DEFAULT_HF_IMAGE_MODEL
    if p == "xai":
        return DEFAULT_XAI_IMAGE_MODEL
    if p == "openai":
        return DEFAULT_OPENAI_IMAGE_MODEL
    return "none"


def slide_image_generation_status() -> tuple[bool, str]:
    if _hf_only_enabled():
        try:
            from huggingface_hub import InferenceClient  # noqa: F401
        except ModuleNotFoundError:
            if not stock_photo_apis_configured() and not (os.getenv("XAI_API_KEY") or "").strip() and not (
                os.getenv("OPENAI_API_KEY") or ""
            ).strip():
                return False, "Install 'huggingface_hub', or set PEXELS_API_KEY / OPENAI_API_KEY for slide image fallbacks."

        if _hf_token():
            return True, "Slide images: Hugging Face first (SLIDE_IMAGE_HF_ONLY=1); optional stock/xAI/OpenAI after HF fails."

        if stock_photo_apis_configured():
            return (
                True,
                "No HF_TOKEN — slides will use Pexels/Unsplash stock (and/or other keys) when HF cannot run.",
            )
        if (os.getenv("XAI_API_KEY") or "").strip() or (os.getenv("OPENAI_API_KEY") or "").strip():
            return True, "No HF_TOKEN — slide images will use xAI/OpenAI when configured (SLIDE_IMAGE_FALLBACK_AFTER_HF=1)."

        return (
            False,
            "Set HF_TOKEN for Hugging Face images, or add PEXELS_API_KEY / UNSPLASH_ACCESS_KEY or XAI_API_KEY / OPENAI_API_KEY.",
        )

    provider = get_slide_image_provider()

    if provider == "placeholder":
        try:
            from PIL import Image, ImageDraw  # noqa: F401
        except ModuleNotFoundError:
            return False, "Install Pillow for local placeholder slide images."

        return (
            True,
            "Local placeholder images will be drawn for each slide (no HF/XAI/OpenAI). "
            "Set SLIDE_IMAGE_NOAPI_PLACEHOLDERS=0 to disable when you add an image API key.",
        )

    if provider == "huggingface":
        try:
            from huggingface_hub import InferenceClient  # noqa: F401
        except ModuleNotFoundError:
            return False, "Install the 'huggingface_hub' package to use Hugging Face slide image generation."

        if not _hf_token():
            return (
                False,
                "Set HF_TOKEN (or HUGGING_FACE_HUB_TOKEN) for Hugging Face inference, "
                "or set SLIDE_IMAGE_PROVIDER to xai/openai with the matching API key.",
            )
        return True, "AI slide image generation is available (Hugging Face Inference)."

    if provider == "xai":
        try:
            from openai import OpenAI  # noqa: F401
        except ModuleNotFoundError:
            return False, "Install the 'openai' package in the active environment to enable AI slide image generation."

        if not os.getenv("XAI_API_KEY"):
            return (
                False,
                "Set XAI_API_KEY for xAI Grok Imagine images, or switch SLIDE_IMAGE_PROVIDER / keys.",
            )
        return True, "AI slide image generation is available (xAI Grok Imagine)."

    if provider == "openai":
        try:
            from openai import OpenAI  # noqa: F401
        except ModuleNotFoundError:
            return False, "Install the 'openai' package in the active environment to enable AI slide image generation."

        if not os.getenv("OPENAI_API_KEY"):
            return False, "Set OPENAI_API_KEY to enable OpenAI slide image generation."
        return True, "AI slide image generation is available (OpenAI)."

    return (
        False,
        "Set HF_TOKEN, XAI_API_KEY, or OPENAI_API_KEY, or SLIDE_IMAGE_PROVIDER=placeholder, "
        "or leave defaults to use local placeholders when no image API keys are set.",
    )


def _slugify(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "").strip("._-")
    return clean or "slide"


# Preset ids sent from the UI (or legacy free-text); expanded for text-to-image models.
SLIDE_IMAGE_STYLE_PRESETS: dict[str, str] = {
    "vector_science": (
        "Highly detailed realistic scientific illustration and educational diagram; clean neutral background; textbook "
        "clarity; topic-specific visualization — avoid cartoon mascot art and unrelated abstract decoration."
    ),
    "illustration": (
        "Polished digital illustration: confident shapes, soft gradients, editorial magazine clarity, "
        "one focal metaphor that matches the slide topic. Avoid clip-art flatness and avoid any typography."
    ),
    "photo": (
        "Photorealistic editorial photograph: natural lighting, shallow depth of field, "
        "believable real-world scene that embodies the topic. No staged stock pose clichés if possible."
    ),
    "abstract": (
        "Abstract modern art: flowing forms, harmonious color fields, subtle symbolism related to the topic, "
        "gallery-quality composition, non-literal but evocative."
    ),
    "3d": (
        "Stylized 3D render: soft global illumination, rounded forms, playful but clear educational tone, "
        "one hero object or miniature scene representing the topic."
    ),
    "line_art": (
        "Elegant line art / ink drawing: high-contrast black lines on light paper texture, "
        "minimal shading, one focal subject, plenty of breathing room."
    ),
    "diagram": (
        "Clean schematic vector diagram: isometric or flat layout, soft shadows, color-coded regions and "
        "simple arrows suggesting flow — imply labels with color only, absolutely no letters or numbers on canvas."
    ),
}


# Keywords in slide text -> extra concrete visual hints for T2I models (still no on-image text).
_TOPIC_VISUAL_HINTS: tuple[tuple[str, str], ...] = (
    (
        "photosynthesis",
        "sunlight through leaves, chloroplast cross-section, CO2 in and O2 out as soft glowing particles, "
        "glucose as subtle golden energy motif",
    ),
    ("chloroplast", "chloroplast cutaway with stacked thylakoids (grana) and stroma, cool blues and greens"),
    ("cell", "simplified plant or animal cell cutaway with major organelles as soft shapes, no labels"),
    ("mitochondria", "mitochondrion with inner membrane folds, warm amber and violet accents"),
    ("dna", "double helix as elegant ribbon, soft laboratory lighting mood without literal lab equipment clutter"),
    ("light", "prism refracting white light into spectrum, clean rays and soft prism glass"),
    ("equation", "balanced symbolic still-life of reactants and products as stylized molecules, no formulas as text"),
    ("calvin", "leaf interior abstract factory mood for Calvin cycle — cycles as gentle circular motion"),
)


def _topic_visual_cues(title: str, bullets_joined: str, document_title: str) -> str:
    blob = f"{title} {bullets_joined} {document_title}".lower()
    lines: list[str] = []
    seen: set[str] = set()
    for key, hint in _TOPIC_VISUAL_HINTS:
        if key in blob and hint not in seen:
            lines.append(hint)
            seen.add(hint)
        if len(lines) >= 4:
            break
    if not lines:
        return ""
    return (
        "TOPIC-SPECIFIC VISUAL CUES (use as props and atmosphere in ONE unified image; never paint words):\n- "
        + "\n- ".join(lines)
    )


def resolve_slide_image_style(image_style: str) -> str:
    """Map short preset ids (or legacy phrases) to a full art-direction block for T2I prompts."""
    raw = (image_style or "").strip().lower()
    if raw in SLIDE_IMAGE_STYLE_PRESETS:
        return SLIDE_IMAGE_STYLE_PRESETS[raw]
    if "vector" in raw and "science" in raw:
        return SLIDE_IMAGE_STYLE_PRESETS["vector_science"]
    if "photoreal" in raw or raw == "photo":
        return SLIDE_IMAGE_STYLE_PRESETS["photo"]
    if "diagram" in raw or "infographic" in raw:
        return SLIDE_IMAGE_STYLE_PRESETS["diagram"]
    if "line" in raw and "art" in raw:
        return SLIDE_IMAGE_STYLE_PRESETS["line_art"]
    if "abstract" in raw:
        return SLIDE_IMAGE_STYLE_PRESETS["abstract"]
    if "3d" in raw:
        return SLIDE_IMAGE_STYLE_PRESETS["3d"]
    if raw:
        return image_style.strip()
    return SLIDE_IMAGE_STYLE_PRESETS["vector_science"]


def _strip_md_bold_for_prompt(text: str) -> str:
    """Remove ``**bold**`` markers so image models read plain nouns."""
    return re.sub(r"\*\*([^*]+)\*\*", r"\1", text or "").strip()


def ensure_slide_image_prompt(slide: dict[str, Any], deck_title: str) -> None:
    """Guarantee a substantive visual brief so **every** T2I call is anchored to this slide's topic."""
    raw = (slide.get("image_prompt") or "").strip()
    if len(raw) >= 48:
        return
    title = (slide.get("title") or slide.get("slide_title") or "Slide").strip()
    bullets = slide.get("bullets") or []
    parts = [_strip_md_bold_for_prompt(str(b)) for b in bullets if isinstance(b, str) and str(b).strip()]
    gist = "; ".join(parts[:3])[:900] if parts else title
    dt = (deck_title or "Presentation").strip()
    slide["image_prompt"] = (
        f"Realistic scientific illustration for «{title}» (deck «{dt}»): highly detailed educational diagram of {gist}. "
        "Clean neutral background; professional textbook-style visual; no readable text in the image."
    )


# Phrases that make T2I models produce generic blobs; replace with title+bullet-grounded scene.
_VAGUE_IMAGE_PROMPT_FRAGMENTS: tuple[str, ...] = (
    "abstract gradient",
    "education abstract",
    "learning journey",
    "innovation",
    "stock image",
    "generic background",
    "technology background",
    "digital transformation",
    "modern tech",
    "colorful gradient",
    "rainbow gradient",
    "minimal flat",
    "concept of learning",
    "business meeting",
    "office workers",
    "handshake",
    "crowd of people",
    "random people",
)

# Rotate composition hints so slides in one deck feel distinct without repeating one generic layout.
_COMPOSITION_VARIETY_HINTS: tuple[str, ...] = (
    "Use a schematic diagram or cross-section that highlights structures from this slide.",
    "Use a clear process-flow or numbered arrow sequence for the steps implied here.",
    "Use an environmental wide shot placing the key objects in realistic context.",
    "Use a tight close-up on one mechanism or structure named on this slide.",
    "Use a split or comparison layout only if bullets contrast two ideas.",
    "Use an isometric or simplified 3/4 educational illustration of the main subject.",
)


def _rewrite_vague_image_prompt_for_style(
    title: str,
    b0: str,
    b_rest: str,
    style_key: str,
) -> str:
    """Concrete scene when the LLM ``image_prompt`` was too vague — must match UI art preset (not always \"science vector\")."""
    tail = (f"{b0}" + (f"; {b_rest}" if b_rest else "")).strip()
    sk = (style_key or "").strip().lower() or "vector_science"
    no_text = "No readable text or labels in the frame."
    if sk == "photo":
        return (
            f"Photorealistic educational photograph of «{title}»: {tail}. Natural lighting, believable environment, "
            f"shallow depth of field where appropriate. {no_text}"
        )
    if sk == "abstract":
        return (
            f"Abstract modern composition evoking «{title}»: {tail}. Cohesive color fields and motion; topic-linked forms, "
            f"non-literal but not random decoration. {no_text}"
        )
    if sk == "3d":
        return (
            f"Stylized 3D educational render of «{title}»: {tail}. Soft global illumination, rounded readable forms, "
            f"one hero subject. {no_text}"
        )
    if sk == "line_art":
        return (
            f"Elegant high-contrast line art / ink drawing of «{title}»: {tail}. Light paper texture; minimal shading. {no_text}"
        )
    if sk == "illustration":
        return (
            f"Polished editorial illustration of «{title}»: {tail}. One clear focal metaphor; magazine clarity; not clip art. {no_text}"
        )
    if sk == "diagram":
        return (
            f"Clean schematic vector diagram for «{title}»: {tail}. Color-coded flow and shapes; imply structure without letters. {no_text}"
        )
    return (
        f"Highly detailed realistic scientific illustration and educational diagram for «{title}»: {tail}. "
        "Clean background; textbook clarity; photorealistic or precise scientific visualization — not cartoon clip art. "
        + no_text
    )


def _sanitize_image_prompt(slide: dict[str, Any], deck_title: str, image_style: str | None = None) -> None:
    """Rewrite weak LLM ``image_prompt`` values so diffusion models get concrete nouns."""
    raw = (slide.get("image_prompt") or "").strip()
    lower = raw.lower()
    title = (slide.get("title") or slide.get("slide_title") or "Slide").strip()
    bullets = slide.get("bullets") or []
    b0 = _strip_md_bold_for_prompt(str(bullets[0]))[:280] if bullets else ""
    b_rest = "; ".join(_strip_md_bold_for_prompt(str(b)) for b in bullets[1:3] if isinstance(b, str) and b.strip())[
        :400
    ]

    words = raw.split()
    looks_vague = any(frag in lower for frag in _VAGUE_IMAGE_PROMPT_FRAGMENTS)
    too_short = len(words) < 14
    if not looks_vague and not too_short:
        return

    slide["image_prompt"] = _rewrite_vague_image_prompt_for_style(title, b0, b_rest, image_style or "vector_science")


def _quality_and_anti_style_lines(image_style: str) -> tuple[str, str]:
    """Opening lines for T2I prompts — must align with UI preset (early tokens dominate HF / SDXL)."""
    sk = (image_style or "").strip().lower() or "vector_science"
    if sk == "photo":
        return (
            "QUALITY: Photorealistic educational photograph; natural lighting; believable scene; sharp subject focus.",
            "ANTI-STYLE: No cartoon mascot clip art; avoid readable text, watermarks, or empty gradient-only frames.",
        )
    if sk == "abstract":
        return (
            "QUALITY: Cohesive abstract composition; color and motion echo the lesson topic; gallery-like clarity.",
            "ANTI-STYLE: No random rainbow noise unrelated to the topic; no readable text or logos.",
        )
    if sk == "3d":
        return (
            "QUALITY: Stylized 3D render with soft global illumination; one clear hero subject tied to the topic.",
            "ANTI-STYLE: No crowded toy clutter; avoid readable text or UI mockups.",
        )
    if sk == "line_art":
        return (
            "QUALITY: High-contrast line art / ink drawing; one focal subject; generous negative space.",
            "ANTI-STYLE: No muddy smudges; avoid readable micro-text or chart axes with letters.",
        )
    if sk == "illustration":
        return (
            "QUALITY: Polished editorial illustration; confident shapes; one focal metaphor matching the topic.",
            "ANTI-STYLE: No preschool doodle style; avoid generic unrelated silhouettes.",
        )
    if sk == "diagram":
        return (
            "QUALITY: Clean schematic diagram or infographic layout; color-coded regions and implied flow without letters.",
            "ANTI-STYLE: No photo clutter or 3D toy renders; avoid readable text in the frame.",
        )
    return (
        "QUALITY: Highly detailed realistic scientific illustration OR precise educational diagram; clean neutral "
        "background; publication-ready clarity; sharp focus.",
        "ANTI-STYLE: No cartoon, anime, children's doodle style, abstract decoration-only blobs unrelated to the topic, "
        "flat mascot clipart, or vague gradient backgrounds unrelated to the topic.",
    )


def _compact_style_directive(image_style: str) -> str:
    """Short style line — long preset paragraphs dilute subject tokens for CLIP / FLUX."""
    raw = (image_style or "").strip().lower()
    one_line: dict[str, str] = {
        "vector_science": (
            "Realistic scientific illustration, highly detailed educational diagram, clean neutral background; "
            "textbook clarity and lighting — never cartoon mascot or flat clipart. Consistent professional educational "
            "style across all slides."
        ),
        "diagram": (
            "Flat schematic diagram: shapes, arrows, color-coded regions suggesting flow — no letters or numbers drawn."
        ),
        "photo": "Photorealistic educational photograph, natural believable scene matching the lesson subject.",
        "illustration": "Polished editorial illustration with one clear focal metaphor tied to the slide topic.",
        "abstract": (
            "Stylized scene where shapes still clearly echo the named lesson subject — not random decoration."
        ),
        "3d": "Soft 3D render illustrating the named subject with rounded forms and gentle lighting.",
        "line_art": "Elegant line drawing focused on one subject from this slide.",
    }
    if raw in one_line:
        return one_line[raw]
    if raw in SLIDE_IMAGE_STYLE_PRESETS:
        block = SLIDE_IMAGE_STYLE_PRESETS[raw]
        return block[:280] + ("…" if len(block) > 280 else "")
    return one_line["vector_science"]


def _compose_topic_first_image_prompt(
    document_title: str,
    slide: dict[str, Any],
    image_style: str,
    *,
    slide_index: int | None = None,
    deck_slide_count: int | None = None,
) -> str:
    """Single prompt for **all** image APIs — topic and scene **first** (CLIP/FLUX attend strongly to early tokens)."""
    ensure_slide_image_prompt(slide, document_title)
    _sanitize_image_prompt(slide, document_title, image_style)

    title = (slide.get("slide_title") or slide.get("title") or "Slide").strip()
    bullets_list = [
        _strip_md_bold_for_prompt(b.strip())
        for b in (slide.get("bullets") or [])
        if isinstance(b, str) and b.strip()
    ]
    bullets_plain = "; ".join(bullets_list)
    llm_scene = _strip_md_bold_for_prompt((slide.get("image_prompt") or "").strip())
    speaker_notes = (slide.get("speaker_notes") or "").strip()
    dt = (document_title or "Presentation").strip()

    # Decks with 6+ slides: Groq returns more (often longer) slide-1 copy → image APIs fail more often without tighter prompts.
    large_deck = bool(deck_slide_count and deck_slide_count >= 6)
    topic_cues = _topic_visual_cues(title, bullets_plain, dt)
    cues_line = ""
    if topic_cues:
        motif_cap = 320 if large_deck else 420
        cues_line = "\nSupporting motifs: " + topic_cues.replace("\n", " ").strip()[:motif_cap]

    style_line = _compact_style_directive(image_style)
    scene_cap = 600 if large_deck else 850
    bullets_cap = 520 if large_deck else 720

    variety_line = ""
    if slide_index is not None:
        hint = _COMPOSITION_VARIETY_HINTS[slide_index % len(_COMPOSITION_VARIETY_HINTS)]
        pos = (
            f"Slide {slide_index + 1} of {deck_slide_count}"
            if deck_slide_count and deck_slide_count > 0
            else f"Slide {slide_index + 1}"
        )
        variety_line = (
            f"\n{pos} — vary layout vs other slides in this deck (same modern educational style): {hint}"
        )
        if large_deck:
            variety_line = f"\n{pos} — {hint}"

    qual, anti = _quality_and_anti_style_lines(image_style)
    # Order matters: subject → scene → bullet nouns → style (keep style compact).
    chunks = [
        qual,
        anti,
        f'MAIN TOPIC (must match this lesson — do not illustrate a different subject): "{title}".',
        f"Primary scene to render: {llm_scene[:scene_cap]}",
        "Ground the visual in these teaching concepts (concrete props, environments, diagram forms, or metaphorical "
        f"shapes implied by the topic): {bullets_plain[:bullets_cap] or title}",
        f"Deck context for mood only: «{dt[:140]}».",
        f"Rendering direction: {style_line}",
        "The image must immediately explain the slide idea to an audience — professional school or university deck.",
        "Hard constraints: single wide composition; absolutely no readable text, letters, numbers, logos, "
        "watermarks, UI, or slide mockups.",
    ]
    body = "\n".join(chunks) + cues_line + variety_line
    if speaker_notes and len(speaker_notes) < 900:
        sn_cap = 320 if large_deck else 500
        body += "\nAdditional facts (do not render as text): " + speaker_notes[:sn_cap]
    return body[:2100] if large_deck else body[:2400]


def _build_prompt(
    document_title: str,
    slide: dict[str, Any],
    image_style: str,
    *,
    slide_index: int | None = None,
    deck_slide_count: int | None = None,
) -> str:
    """Backward-compatible alias — all backends use topic-first composition."""
    return _compose_topic_first_image_prompt(
        document_title,
        slide,
        image_style,
        slide_index=slide_index,
        deck_slide_count=deck_slide_count,
    )


def _default_hf_negative_prompt() -> str:
    return (
        "text, words, letters, typography, watermark, logo, signature, low quality, blurry, "
        "ugly, deformed, extra limbs, screenshot, browser, phone frame, slide template, "
        "PowerPoint, title bar, bullet list, chart axes labels, crowded collage, "
        "generic staged stock-photo clichés, business handshake scene, cheesy mascot, flat icon grid, UI mockup, smartphone frame, "
        "meaningless abstract gradient blobs unrelated to topic, decorative noise panels, generic rainbow wallpaper, "
        "wrong science topic, unrelated subject matter, random shapes not tied to lesson, "
        "generic purple-blue abstract wallpaper, clipart montage, unrelated metaphor, "
        "technology background, digital transformation buzzword art, random business people, office crowd, "
        "irrelevant landscape, generic medical stock, hacker in hoodie cliché unrelated to slide, "
        "cartoon, anime, chibi, children's illustration, preschool drawing, cute mascot, flat vector clipart, "
        "simple shapes only, doodle style, emoji style, Pixar exaggerated characters, puppet style"
    )


# Minimal valid 1×1 PNG — last resort if Pillow cannot draw a per-slide variant.
_FALLBACK_TINY_PNG = base64.standard_b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def live_slide_placeholder_data_url(slide_index: int) -> str:
    """Tiny distinct PNG data URL for text-only slides — satisfies export/deck validation without a hero image."""
    png = _distinct_fallback_png(slide_index)
    b64 = base64.standard_b64encode(png).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _distinct_fallback_png(slide_index: int) -> bytes:
    """Small solid PNG unique per index (avoids duplicate-data-url assert when APIs all fail)."""
    try:
        from PIL import Image

        r = (37 + slide_index * 41) % 220
        g = (61 + slide_index * 17) % 220
        b = (83 + slide_index * 29) % 220
        im = Image.new("RGB", (8, 8), (r, g, b))
        buf = BytesIO()
        im.save(buf, format="PNG")
        out = buf.getvalue()
        return out if len(out) >= len(_FALLBACK_TINY_PNG) else _FALLBACK_TINY_PNG
    except Exception:
        return _FALLBACK_TINY_PNG


def _coerce_png_bytes(raw: bytes) -> bytes:
    """Normalize JPEG/WebP/etc. to PNG bytes for stable .pptx embedding."""
    if len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        return raw
    try:
        from PIL import Image

        image = Image.open(BytesIO(raw))
        out = BytesIO()
        if image.mode in ("RGBA", "LA", "P"):
            image.save(out, format="PNG")
        else:
            image.convert("RGB").save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return raw


def generate_hf_slide_image_file(prompt: str, output_path: str | Path) -> str:
    """Generate one slide image via Hugging Face Inference API; write PNG to disk (no placeholder).

    Raises ``RuntimeError`` if ``HF_TOKEN`` is missing or the model returns no image.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw, _ = _generate_huggingface_image(prompt)
    if not raw:
        raise RuntimeError(
            "Hugging Face image generation failed or returned empty bytes. "
            "Set HF_TOKEN (and optionally HF_IMAGE_MODEL), install huggingface_hub, and retry."
        )
    path.write_bytes(_coerce_png_bytes(raw))
    return str(path.resolve())


def _save_generated_image(document_id: str, slide_index: int, image_bytes: bytes) -> str:
    png_bytes = _coerce_png_bytes(image_bytes)
    target_dir = get_generated_images_dir() / _slugify(document_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"generated_slide_{slide_index + 1}.png"
    target_path.write_bytes(png_bytes)
    return str(target_path)


def _decode_image_response(first: Any) -> tuple[bytes | None, str | None]:
    from urllib.error import HTTPError, URLError
    from urllib.request import urlopen

    payload = getattr(first, "b64_json", None)
    if payload:
        return base64.b64decode(payload), getattr(first, "revised_prompt", None)

    url = getattr(first, "url", None)
    if url:
        try:
            with urlopen(url, timeout=120) as resp:
                body = resp.read()
            if body:
                return body, getattr(first, "revised_prompt", None)
        except (HTTPError, URLError, TimeoutError, OSError):
            return None, getattr(first, "revised_prompt", None)

    return None, getattr(first, "revised_prompt", None)


def _hf_inference_api_rest_image(
    model_id: str,
    prompt_use: str,
    timeout: float,
) -> bytes | None:
    """POST ``https://api-inference.huggingface.co/models/<id>`` with ``{\"inputs\": prompt}``.

    Same contract as the JS sample: ``Authorization: Bearer <HF_TOKEN>``, JSON body ``inputs``.
    Retries once on non-image / HTTP errors (cold start 503, etc.).
    """
    log = logging.getLogger(__name__)
    token = _hf_token()
    if not token:
        return None
    mid = model_id.strip().strip("/")
    url = f"https://api-inference.huggingface.co/models/{mid}"
    headers = {"Authorization": f"Bearer {token}"}
    payload: dict[str, Any] = {"inputs": prompt_use[:1500]}
    log.info("HF Inference REST prompt_preview=%s model=%s", prompt_use[:120].replace("\n", " "), mid)

    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            log.info("HF Inference REST status=%s model=%s attempt=%s", resp.status_code, mid, attempt + 1)
            if resp.status_code != 200:
                log.warning("HF Inference REST error: %s", (resp.text or "")[:900])
                continue

            body = resp.content or b""
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if body.startswith(b"{") or ("application/json" in ctype and len(body) < 4000):
                log.warning("HF Inference REST JSON (not image): %s", body[:900])
                continue
            if len(body) > 200:
                return body
        except Exception as exc:
            log.warning("HF Inference REST request failed model=%s: %s", mid, exc)
            continue
    return None


def _pil_image_to_png_bytes(image: Any) -> bytes:
    out = BytesIO()
    if getattr(image, "mode", None) in ("RGBA", "P", "LA"):
        image.save(out, format="PNG")
    else:
        image.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def _generate_huggingface_image(prompt: str) -> tuple[bytes | None, str | None]:
    """Hugging Face Hub text-to-image (InferenceClient).

    FLUX and many Router models **reject** ``negative_prompt`` / extra kwargs — those caused silent failure
    (exceptions swallowed → gradient placeholders). We try **minimal** ``text_to_image`` calls first; optional
    extended kwargs only when ``HF_IMAGE_EXTENDED_PARAMS=1``.
    """
    log = logging.getLogger(__name__)
    from huggingface_hub import InferenceClient

    model = (os.getenv("HF_IMAGE_MODEL") or DEFAULT_HF_IMAGE_MODEL).strip()
    token = _hf_token()
    if not token:
        return None, None

    provider_raw = (os.getenv("HF_INFERENCE_PROVIDER") or "auto").strip() or "auto"
    try:
        timeout = float((os.getenv("HF_INFERENCE_TIMEOUT") or "75").strip() or "75")
    except ValueError:
        timeout = 75.0
    timeout = max(25.0, min(600.0, timeout))

    client = InferenceClient(model=model, token=token, timeout=timeout, provider=provider_raw)  # type: ignore[arg-type]

    try:
        max_chars = max(256, min(4000, int((os.getenv("HF_IMAGE_PROMPT_MAX_CHARS") or "1600").strip() or "1600")))
    except ValueError:
        max_chars = 1600
    prompt_use = (prompt or "").strip()
    if len(prompt_use) > max_chars:
        prompt_use = prompt_use[: max_chars - 3] + "..."

    width = max(64, min(2048, int(os.getenv("HF_IMAGE_WIDTH", "1024"))))
    height = max(64, min(2048, int(os.getenv("HF_IMAGE_HEIGHT", "576"))))

    attempts: list[tuple[str, Any]] = []

    if _env_flag("HF_IMAGE_EXTENDED_PARAMS", False):
        neg_env = (os.getenv("HF_IMAGE_NEGATIVE_PROMPT") or "").strip()
        neg = neg_env if neg_env else _default_hf_negative_prompt()
        kwargs: dict[str, Any] = {"width": width, "height": height, "negative_prompt": neg}
        steps_env = (os.getenv("HF_IMAGE_NUM_INFERENCE_STEPS") or "").strip()
        guidance_env = (os.getenv("HF_IMAGE_GUIDANCE_SCALE") or "").strip()
        if steps_env.isdigit():
            kwargs["num_inference_steps"] = int(steps_env)
        try:
            if guidance_env:
                kwargs["guidance_scale"] = float(guidance_env)
            else:
                kwargs["guidance_scale"] = float(os.getenv("HF_IMAGE_GUIDANCE_SCALE", "6.5"))
        except ValueError:
            kwargs["guidance_scale"] = 6.5
        attempts.append(("extended_kwargs", lambda k=kwargs: client.text_to_image(prompt_use, **k)))

    # Compatible path for FLUX / most Inference API models (prompt + size only).
    attempts.append(("width_height", lambda: client.text_to_image(prompt_use, width=width, height=height)))
    attempts.append(("prompt_only", lambda: client.text_to_image(prompt_use)))

    short_p = prompt_use[:900] if len(prompt_use) > 900 else prompt_use
    sw, sh = min(width, 768), min(height, 432)
    attempts.append(("short_prompt_sized", lambda: client.text_to_image(short_p, width=sw, height=sh)))

    fallback_model = (os.getenv("HF_IMAGE_FALLBACK_MODEL") or "").strip()
    last_exc: Exception | None = None
    for tag, fn in attempts:
        try:
            image = fn()
            if image is not None:
                return _pil_image_to_png_bytes(image), None
        except Exception as exc:
            last_exc = exc
            log.warning("HF text_to_image failed [%s] model=%s: %s", tag, model, exc)

    if fallback_model and fallback_model != model:
        try:
            fb_client = InferenceClient(
                model=fallback_model, token=token, timeout=timeout, provider=provider_raw  # type: ignore[arg-type]
            )
            image = fb_client.text_to_image(prompt_use, width=min(width, 1024), height=min(height, 576))
            if image is not None:
                return _pil_image_to_png_bytes(image), None
        except Exception as exc:
            last_exc = exc
            log.warning("HF fallback model %s failed: %s", fallback_model, exc)

    # Classic Inference API (raw HTTP) — many users get empty results from Router/Client only; REST returns image/png.
    tried_rest: set[str] = set()
    for mid in (model, *_HF_REST_FALLBACK_MODELS, fallback_model or ""):
        mid = (mid or "").strip()
        if not mid or mid in tried_rest:
            continue
        tried_rest.add(mid)
        raw_bytes = _hf_inference_api_rest_image(mid, prompt_use, timeout)
        if raw_bytes:
            return _coerce_png_bytes(raw_bytes), None

    if last_exc:
        log.warning("HF image generation returned no pixels; last error: %s", last_exc)
    return None, None


def _generate_xai_image(prompt: str) -> tuple[bytes | None, str | None]:
    """xAI Grok Imagine via OpenAI-compatible ``images.generate`` (see xAI image generation docs)."""
    from openai import OpenAI

    client = OpenAI(
        base_url=DEFAULT_XAI_API_BASE,
        api_key=os.environ["XAI_API_KEY"],
    )
    model = DEFAULT_XAI_IMAGE_MODEL
    aspect_ratio = (os.getenv("XAI_IMAGE_ASPECT_RATIO") or "16:9").strip()
    resolution = (os.getenv("XAI_IMAGE_RESOLUTION") or "1k").strip()

    response = client.images.generate(
        model=model,
        prompt=prompt,
        n=1,
        response_format="b64_json",
        extra_body={"aspect_ratio": aspect_ratio, "resolution": resolution},
    )

    if not getattr(response, "data", None):
        return None, None

    return _decode_image_response(response.data[0])


def _resolve_image_try_order() -> list[str]:
    """Backend ids to attempt, in order.

    - ``SLIDE_IMAGE_TRY_ORDER`` always wins when set (comma-separated: huggingface, hf, xai, openai).
    - If **unset** and ``SLIDE_IMAGE_PROVIDER`` is a single cloud provider, only that one is used.
    - If **unset** and no explicit provider (auto mode), try HF → xAI → OpenAI so one dead quota does not block others.
    """
    order_env = (os.getenv("SLIDE_IMAGE_TRY_ORDER") or "").strip().lower()
    if order_env:
        return [x.strip() for x in order_env.replace(" ", "").split(",") if x.strip()]
    explicit = (os.getenv("SLIDE_IMAGE_PROVIDER") or "").strip().lower()
    if explicit in ("huggingface", "hf"):
        return ["huggingface"]
    if explicit == "xai":
        return ["xai"]
    if explicit == "openai":
        return ["openai"]
    return ["huggingface", "xai", "openai"]


def _generate_image_try_all_providers(prompt: str) -> tuple[bytes | None, str | None]:
    """Try each image backend that has credentials, in resolved order.

    When Hugging Face returns 402 / empty, xAI or OpenAI can still succeed if keys exist (auto mode only).
    Runs the full chain **multiple rounds** (default 2) so transient quota/rate hits do not leave half the deck on placeholders.
    """
    import time

    rounds = max(1, min(5, int((os.getenv("SLIDE_IMAGE_FULL_CHAIN_RETRIES") or "1").strip() or "1")))
    alias = {"hf": "huggingface"}
    for round_i in range(rounds):
        ids = _resolve_image_try_order()
        for token in ids:
            key = alias.get(token, token)
            if key == "huggingface":
                if not _hf_token():
                    continue
                try:
                    raw, rev = _generate_huggingface_image(prompt)
                    if raw:
                        return raw, rev
                except Exception:
                    continue
            elif key == "xai":
                if not (os.getenv("XAI_API_KEY") or "").strip():
                    continue
                try:
                    raw, rev = _generate_xai_image(prompt)
                    if raw:
                        return raw, rev
                except Exception:
                    continue
            elif key == "openai":
                if not (os.getenv("OPENAI_API_KEY") or "").strip():
                    continue
                try:
                    raw, rev = _generate_openai_image(prompt)
                    if raw:
                        return raw, rev
                except Exception:
                    continue
        if round_i + 1 < rounds:
            time.sleep(0.35 + round_i * 0.25)
    return None, None


def _generate_ai_skip_hf(prompt: str) -> tuple[bytes | None, str | None]:
    """xAI then OpenAI — avoids hammering Hugging Face after quota / 402 failures."""
    if (os.getenv("XAI_API_KEY") or "").strip():
        try:
            raw, rev = _generate_xai_image(prompt)
            if raw:
                return raw, rev
        except Exception:
            pass
    if (os.getenv("OPENAI_API_KEY") or "").strip():
        try:
            raw, rev = _generate_openai_image(prompt)
            if raw:
                return raw, rev
        except Exception:
            pass
    return None, None


def _generate_openai_image(prompt: str) -> tuple[bytes | None, str | None]:
    """OpenAI DALL·E / GPT image models (default OpenAI API host)."""
    from openai import OpenAI

    client = OpenAI()
    model = (DEFAULT_OPENAI_IMAGE_MODEL or "gpt-image-1").strip()

    if model.startswith("gpt-image"):
        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=DEFAULT_OPENAI_IMAGE_SIZE,
            quality=DEFAULT_OPENAI_IMAGE_QUALITY,
            output_format="png",
            n=1,
        )
    elif model.startswith("dall-e-3"):
        size = (
            DEFAULT_OPENAI_IMAGE_SIZE
            if DEFAULT_OPENAI_IMAGE_SIZE in ("1024x1024", "1792x1024", "1024x1792")
            else "1024x1024"
        )
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality="standard",
            response_format="b64_json",
            n=1,
        )
    else:
        response = client.images.generate(
            model=model if model.startswith("dall-e") else "dall-e-2",
            prompt=prompt,
            size="1024x1024",
            response_format="b64_json",
            n=1,
        )

    if not getattr(response, "data", None):
        return None, None

    return _decode_image_response(response.data[0])


def _placeholder_topic_blob(slide: dict[str, Any], document_title: str) -> str:
    title = (slide.get("slide_title") or slide.get("title") or "").strip()
    bullets = slide.get("bullets") or []
    joined = " ".join(str(b) for b in bullets if isinstance(b, str) and b.strip())
    ip = (slide.get("image_prompt") or "").strip()
    return f"{title} {document_title} {joined} {ip}".lower()


def _apply_blob_tinted_background(draw, width: int, height: int, blob: str) -> None:
    """Vertical wash — hue comes from SHA256(blob) so each slide's preview matches its unique topic text."""
    d = hashlib.sha256(blob.encode("utf-8")).digest()
    br, bg_, bb = 225 + d[0] % 22, 235 + d[1] % 18, 246 + d[2] % 12
    for x in range(0, width, 6):
        t = x / max(width, 1)
        r = int(br + t * (12 + d[3] % 14))
        g = int(bg_ - t * (8 + d[4] % 10))
        b = int(bb - t * (6 + d[5] % 8))
        draw.line([(x, 0), (x, height)], fill=(r, g, b), width=6)


def _generate_placeholder_image_bytes(
    slide: dict[str, Any],
    document_title: str,
    image_style: str,
    slide_index: int,
) -> bytes:
    """Wide 16:9 PNG when no image API is configured and stock photo fetch also failed.

    Only a topic-tinted neutral wash (no clip-art); set Pexels/Unsplash keys for real photos.
    """
    from PIL import Image, ImageDraw

    width, height = 1536, 864
    ensure_slide_image_prompt(slide, document_title)
    _sanitize_image_prompt(slide, document_title, image_style)

    # Last resort: try stock again, then a neutral gradient (no cartoon shapes — looks less like a toy slide).
    if _stock_mix_enabled():
        sb_raw, _ = fetch_stock_photo_bytes(slide, document_title, slide_index)
        if sb_raw:
            return _coerce_png_bytes(sb_raw)

    image = Image.new("RGB", (width, height), color=(245, 250, 255))
    draw = ImageDraw.Draw(image)
    blob = _placeholder_topic_blob(slide, document_title)
    _apply_blob_tinted_background(draw, width, height, blob)

    try:
        from PIL import ImageFont

        font = ImageFont.load_default()

        title = (slide.get("slide_title") or slide.get("title") or "Slide").strip() or "Slide"
        caption_lines = textwrap.wrap(title, width=56)[:4]
        ink = (71, 85, 105)
        sub = (
            "Local preview — Hugging Face / Pollinations did not return AI pixels "
            "(check HF_TOKEN, billing at hf.co, firewall, HF_IMAGE_MODEL)."
        )
        y = int(height * 0.34)
        line_h = 18
        for line in caption_lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            draw.text(((width - tw) / 2, y), line, fill=ink, font=font)
            line_h = max(14, bbox[3] - bbox[1] + 6)
            y += line_h
        y += 12
        for subline in textwrap.wrap(sub, width=72)[:3]:
            bbox = draw.textbbox((0, 0), subline, font=font)
            tw = bbox[2] - bbox[0]
            draw.text(((width - tw) / 2, y), subline, fill=(100, 116, 139), font=font)
            y += max(14, bbox[3] - bbox[1] + 4)
    except Exception:
        pass

    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _stock_mix_enabled() -> bool:
    if _hf_only_enabled():
        return False
    raw = (os.getenv("SLIDE_IMAGE_MIX_ENABLE") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _slide_mix_stock_first(slide_index: int) -> bool:
    """Default: realistic web photos first on every slide; use ``alternate`` only when explicitly set."""
    mode = (os.getenv("SLIDE_IMAGE_MIX_MODE") or "stock_first").strip().lower()
    if mode in ("alternate", "mixed"):
        return slide_index % 2 == 0
    if mode == "ai_first":
        return False
    # stock_first, stock_preferred, realistic_web_first, empty
    return True


def _stock_on_ai_fail_enabled() -> bool:
    """After HF / Pollinations / other AI paths fail: search Pexels & Unsplash (requires API keys).

    ``SLIDE_IMAGE_STOCK_ON_AI_FAIL=0`` disables this last-resort stock step.
    """
    if not stock_photo_apis_configured():
        return False
    raw = (os.getenv("SLIDE_IMAGE_STOCK_ON_AI_FAIL") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _fallback_stock_or_placeholder_bytes(
    slide: dict[str, Any],
    document_title: str,
    image_style: str,
    slide_index: int,
) -> tuple[bytes, str | None]:
    """Prefer royalty-free stock (web APIs) over the Pillow gradient when AI produced nothing."""
    if _stock_on_ai_fail_enabled():
        sb_raw, st_src = fetch_stock_photo_bytes(slide, document_title, slide_index)
        if sb_raw:
            return _coerce_png_bytes(sb_raw), f"stock:{st_src}"
    out = _generate_placeholder_image_bytes(slide, document_title, image_style, slide_index)
    return out, None


def _compact_retry_prompt(document_title: str, slide: dict[str, Any], image_style: str) -> str:
    """Shorter prompt when the full brief returns nothing (HF quota, length limits, timeouts)."""
    title = (slide.get("slide_title") or slide.get("title") or "Slide").strip()
    bullets = slide.get("bullets") or []
    gist = "; ".join(
        _strip_md_bold_for_prompt(str(b))[:140] for b in bullets[:4] if isinstance(b, str) and str(b).strip()
    )
    dt = (document_title or "Presentation").strip()
    style = _compact_style_directive(image_style)
    return (
        f"Highly detailed realistic scientific illustration, educational diagram, clean neutral background. "
        f'Subject: "{title}". Teaching focus: {gist[:520]}. Deck: {dt[:80]}. {style} '
        "Single composition, no readable text, no watermark."
    )[:1100]


def _pollinations_fallback_enabled() -> bool:
    """Free image generation via Pollinations (no API key). Disable with SLIDE_IMAGE_POLLINATIONS_FALLBACK=0."""
    raw = (os.getenv("SLIDE_IMAGE_POLLINATIONS_FALLBACK") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _sanitize_prompt_for_pollinations(text: str) -> str:
    """Safe single-line prompt for Pollinations URL path."""
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", text or "")
    t = re.sub(r"[^\w\s,.;:\-/]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:950] if t else "realistic educational scientific illustration"


def _pollinations_first_enabled() -> bool:
    """Try free Pollinations **before** Hugging Face when ``SLIDE_IMAGE_POLLINATIONS_FIRST=1`` (no HF billing)."""
    raw = (os.getenv("SLIDE_IMAGE_POLLINATIONS_FIRST") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _generate_pollinations_image(prompt: str, *, seed: int | None = None) -> tuple[bytes | None, str | None]:
    """Pollinations image.pollinations.ai — works without HF quota or paid keys (public HTTP endpoint)."""
    log = logging.getLogger(__name__)
    if not _pollinations_fallback_enabled():
        return None, None
    from urllib.parse import quote
    from urllib.request import Request, urlopen

    q = _sanitize_prompt_for_pollinations(prompt)
    if len(q) < 16:
        q = "detailed realistic educational scientific illustration, clean studio background, professional"
    path_q = quote(q, safe="")
    try:
        w = max(512, min(1536, int((os.getenv("POLLINATIONS_IMAGE_WIDTH") or "1024").strip() or "1024")))
        h = max(288, min(1536, int((os.getenv("POLLINATIONS_IMAGE_HEIGHT") or "576").strip() or "576")))
    except ValueError:
        w, h = 1024, 576
    url = f"https://image.pollinations.ai/prompt/{path_q}?width={w}&height={h}&nologo=true"
    if seed is not None:
        url += f"&seed={abs(int(seed)) % 2_000_000_000}"
    try:
        req = Request(url, headers={"User-Agent": "SmartTeacherAssistant/1.1"})
        try:
            poll_to = float((os.getenv("POLLINATIONS_TIMEOUT") or "50").strip() or "50")
        except ValueError:
            poll_to = 50.0
        poll_to = max(18.0, min(240.0, poll_to))
        with urlopen(req, timeout=poll_to) as resp:
            body = resp.read()
        if body and len(body) > 800:
            return _coerce_png_bytes(body), "pollinations"
    except Exception as exc:
        log.warning("Pollinations image fallback failed: %s", exc)
    return None, None


def _generate_single_image(
    slide: dict[str, Any],
    document_title: str,
    image_style: str,
    slide_index: int,
    deck_slide_count: int | None = None,
) -> tuple[bytes | None, str | None]:
    """Default (SLIDE_IMAGE_HF_ONLY=1): Hugging Face only, with retries. Legacy: optional stock + multi-provider AI."""
    prompt = _compose_topic_first_image_prompt(
        document_title,
        slide,
        image_style,
        slide_index=slide_index,
        deck_slide_count=deck_slide_count,
    )

    # 6+ slides: try compact Pollinations before HF — long slide-1 text often breaks HF first; short URL usually works.
    if (
        deck_slide_count is not None
        and deck_slide_count >= 6
        and _pollinations_fallback_enabled()
        and not _pollinations_first_enabled()
    ):
        compact_early = _compact_retry_prompt(document_title, slide, image_style)
        early_p, early_m = _generate_pollinations_image(
            compact_early, seed=slide_index * 47_311 + (deck_slide_count or 0) * 17
        )
        if early_p:
            return early_p, early_m or "pollinations"

    # Free tier first: Pollinations needs no API key (set SLIDE_IMAGE_POLLINATIONS_FIRST=1).
    if _pollinations_first_enabled() and _pollinations_fallback_enabled():
        pol_px, pol_meta = _generate_pollinations_image(prompt, seed=slide_index * 17_917 + 3)
        if pol_px:
            return pol_px, pol_meta
        compact_pf = _compact_retry_prompt(document_title, slide, image_style)
        pol_px2, pol_meta2 = _generate_pollinations_image(
            compact_pf, seed=slide_index * 91_087 + 11
        )
        if pol_px2:
            return pol_px2, pol_meta2 or "pollinations"

    if _hf_only_enabled():
        if _hf_token():
            n = _hf_retries_per_slide()
            variations = (
                "",
                "\nVariation: alternate camera angle; same scientific subject; highly detailed educational clarity.",
                "\nVariation: emphasize textbook-style diagram structure without any readable letters in the frame.",
                "\nVariation: macro emphasis on structures and processes named on this slide.",
                "\nVariation: wider scene showing realistic context for the same lesson concept.",
            )
            for attempt in range(n):
                suffix = variations[attempt % len(variations)]
                p = prompt if not suffix else prompt + suffix
                raw, rev = _generate_huggingface_image(p)
                if raw:
                    return raw, rev

        if _hf_fallback_after_hf_failure_enabled():
            sb_raw, st_src = fetch_stock_photo_bytes(slide, document_title, slide_index)
            if sb_raw:
                return _coerce_png_bytes(sb_raw), f"stock:{st_src}"
            raw_ai, rev_ai = _generate_ai_skip_hf(prompt)
            if raw_ai:
                return raw_ai, rev_ai

        compact_h = _compact_retry_prompt(document_title, slide, image_style)
        pol_h, pol_m = _generate_pollinations_image(compact_h, seed=slide_index * 13_333 + 1)
        if pol_h:
            return pol_h, pol_m

        try:
            ensure_slide_image_prompt(slide, document_title)
            _sanitize_image_prompt(slide, document_title, image_style)
            b, m = _fallback_stock_or_placeholder_bytes(
                slide, document_title, image_style, slide_index
            )
            return b, m
        except Exception:
            return None, None

    provider = get_slide_image_provider()

    def run_ai(ai_prompt: str) -> tuple[bytes | None, str | None]:
        if _env_flag("SLIDE_IMAGE_TRY_ALL_PROVIDERS", True):
            return _generate_image_try_all_providers(ai_prompt)
        if provider == "placeholder" and (
            _hf_token() or (os.getenv("XAI_API_KEY") or "").strip() or (os.getenv("OPENAI_API_KEY") or "").strip()
        ):
            return _generate_image_try_all_providers(ai_prompt)
        if provider == "huggingface":
            return _generate_huggingface_image(ai_prompt)
        if provider == "xai":
            return _generate_xai_image(ai_prompt)
        if provider == "openai":
            return _generate_openai_image(ai_prompt)
        return None, None

    def run_ai_with_compact_fallback(ai_prompt: str) -> tuple[bytes | None, str | None]:
        raw, rev = run_ai(ai_prompt)
        if raw:
            return raw, rev
        compact = _compact_retry_prompt(document_title, slide, image_style)
        raw2, rev2 = run_ai(compact)
        if raw2:
            return raw2, rev2
        pol_r, pol_m = _generate_pollinations_image(compact, seed=slide_index * 79_907 + 2)
        if pol_r:
            return pol_r, pol_m
        return None, None

    stock_png = None
    st_src = ""
    if _stock_mix_enabled():
        sb_raw, st_src = fetch_stock_photo_bytes(slide, document_title, slide_index)
        if sb_raw:
            stock_png = _coerce_png_bytes(sb_raw)

    stock_first = _slide_mix_stock_first(slide_index)

    if stock_first and stock_png:
        return stock_png, f"stock:{st_src}"

    # Resolved "placeholder" still try cloud APIs when keys exist (.env loaded late, or SLIDE_IMAGE_PROVIDER misuse).
    if provider == "placeholder":
        if _hf_token() or (os.getenv("XAI_API_KEY") or "").strip() or (os.getenv("OPENAI_API_KEY") or "").strip():
            raw_cf, rev_cf = run_ai_with_compact_fallback(prompt)
            if raw_cf:
                return raw_cf, rev_cf
        compact_ph = _compact_retry_prompt(document_title, slide, image_style)
        pol_ph, pol_pm = _generate_pollinations_image(compact_ph, seed=slide_index * 101_087 + 9)
        if pol_ph:
            return pol_ph, pol_pm

    if provider == "placeholder":
        ensure_slide_image_prompt(slide, document_title)
        _sanitize_image_prompt(slide, document_title, image_style)
        b, m = _fallback_stock_or_placeholder_bytes(slide, document_title, image_style, slide_index)
        return b, m

    if stock_first:
        raw, rev = run_ai_with_compact_fallback(prompt)
        if raw:
            return raw, rev
        if stock_png:
            return stock_png, f"stock:{st_src}"
        try:
            ensure_slide_image_prompt(slide, document_title)
            _sanitize_image_prompt(slide, document_title, image_style)
            b, m = _fallback_stock_or_placeholder_bytes(
                slide, document_title, image_style, slide_index
            )
            return b, m
        except Exception:
            return None, None

    raw, rev = run_ai_with_compact_fallback(prompt)
    if raw:
        return raw, rev
    if stock_png:
        return stock_png, f"stock:{st_src}"
    try:
        ensure_slide_image_prompt(slide, document_title)
        _sanitize_image_prompt(slide, document_title, image_style)
        b, m = _fallback_stock_or_placeholder_bytes(slide, document_title, image_style, slide_index)
        return b, m
    except Exception:
        return None, None


def _catalog_id_to_path(catalog: list[dict[str, Any]]) -> dict[str, str]:
    """Map image_id -> existing filesystem path for assets already in the catalog."""
    out: dict[str, str] = {}
    for item in catalog:
        iid = item.get("image_id")
        p = item.get("asset_path") or item.get("path")
        if not iid or not p:
            continue
        ps = str(p).strip()
        if ps and Path(ps).is_file():
            out[str(iid)] = ps
    return out


def is_valid_live_slide_data_url(s: str) -> bool:
    """Non-empty image data URL: case-insensitive ``base64,``, decodes to PNG/JPEG-ish or any non-trivial bytes."""
    if not isinstance(s, str) or not s.strip():
        return False
    low = s.lower()
    marker = "base64,"
    if marker not in low:
        return False
    idx = low.index(marker)
    b64 = s[idx + len(marker) :].strip().strip('"').replace("\n", "").replace("\r", "")
    if not b64:
        return False
    try:
        raw = base64.standard_b64decode(b64, validate=False)
        if len(raw) >= 67:
            return True
        if len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n":
            return True
        if len(raw) >= 3 and raw[:3] == b"\xff\xd8\xff":
            return True
        return len(raw) >= 32
    except Exception:
        try:
            raw2 = base64.urlsafe_b64decode(b64 + "==")
            return len(raw2) >= 32
        except Exception:
            return False


def teacher_slide_has_resolved_image(slide: dict[str, Any], catalog: list[dict[str, Any]]) -> bool:
    pmap = _catalog_id_to_path(catalog)
    refs = [r for r in (slide.get("image_refs") or []) if isinstance(r, str)]
    return bool(refs) and any(pmap.get(r) for r in refs)


def assert_live_slide_deck_payload(slides: list[dict[str, Any]]) -> None:
    """Raise if any slide lacks a usable PNG data URL or duplicates another slide's image bytes."""
    missing = [
        i
        for i, sl in enumerate(slides)
        if not is_valid_live_slide_data_url(
            (sl.get("image") if isinstance(sl.get("image"), str) else "") or ""
        )
    ]
    if missing:
        raise RuntimeError(
            "Live slide deck invariant: every slide must have exactly one image (PNG data URL). "
            f"Missing or invalid image field at slide indices (0-based): {missing}"
        )
    seen_at: dict[str, int] = {}
    for i, sl in enumerate(slides):
        img = sl.get("image") if isinstance(sl.get("image"), str) else ""
        if img in seen_at:
            raise RuntimeError(
                "Live slide deck invariant: each slide must have a distinct image. "
                f"Slides {seen_at[img] + 1} and {i + 1} share identical image data."
            )
        seen_at[img] = i


def assert_teacher_slides_have_catalog_images(slides: list[dict[str, Any]], catalog: list[dict[str, Any]]) -> None:
    """Raise if any slide lacks a catalog image path via image_refs."""
    missing: list[int] = []
    pmap = _catalog_id_to_path(catalog)
    for i, sl in enumerate(slides):
        refs = [r for r in (sl.get("image_refs") or []) if isinstance(r, str)]
        if not refs or not any(pmap.get(r) for r in refs):
            missing.append(i)
    if missing:
        raise RuntimeError(
            "Slide deck invariant: each slide must have exactly one generated/stored image in the catalog. "
            f"Unresolved slides (0-based indices): {missing}"
        )


def _generate_one_slide_attachment(
    document_id: str,
    document_title: str,
    base_slide: dict[str, Any],
    slide_index: int,
    deck_slide_count: int,
    image_style: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[str], bool]:
    """Build one slide image + catalog row. Used sequentially or from worker threads."""
    slide = dict(base_slide)
    notes: list[str] = []
    counted = False
    slide["image_refs"] = []

    ensure_slide_image_prompt(slide, document_title)
    used_api_placeholder = False
    try:
        image_bytes, revised_prompt = _generate_single_image(
            slide,
            document_title,
            image_style,
            slide_index,
            deck_slide_count=deck_slide_count,
        )
    except Exception as exc:
        if _env_flag("SLIDE_IMAGE_FALLBACK_PLACEHOLDERS", False):
            try:
                image_bytes = _generate_placeholder_image_bytes(
                    slide, document_title, image_style, slide_index
                )
                revised_prompt = None
                used_api_placeholder = True
                notes.append(
                    f"Slide {slide_index + 1}: image API failed ({exc!s}); used local placeholder. "
                    "Fix keys/model or set SLIDE_IMAGE_FALLBACK_PLACEHOLDERS=0 to stop masking errors."
                )
            except Exception:
                notes.append(f"AI image generation failed for slide {slide_index + 1}: {exc}")
                return slide, None, notes, False
        else:
            notes.append(f"AI image generation failed for slide {slide_index + 1}: {exc}")
            return slide, None, notes, False

    if not image_bytes:
        if _env_flag("SLIDE_IMAGE_LAST_RESORT_PLACEHOLDER", True):
            try:
                image_bytes = _generate_placeholder_image_bytes(
                    slide, document_title, image_style, slide_index
                )
                revised_prompt = None
                used_api_placeholder = True
                notes.append(
                    f"Slide {slide_index + 1}: image APIs returned nothing — used local PNG preview. "
                    "Optional: set HF_TOKEN for AI images or adjust HF_IMAGE_MODEL / quota."
                )
            except Exception:
                notes.append(f"AI image generation returned no image for slide {slide_index + 1}.")
                return slide, None, notes, False
        else:
            raise RuntimeError(
                f"No image for slide {slide_index + 1}: HF exhausted and fallbacks failed. "
                "Set SLIDE_IMAGE_LAST_RESORT_PLACEHOLDER=1 or configure stock / backup APIs."
            )

    image_id = f"generated_slide_{slide_index + 1}"
    asset_path = _save_generated_image(document_id, slide_index, image_bytes)
    slide["image"] = asset_path
    provider_now = get_slide_image_provider()
    is_local_visual = provider_now == "placeholder" or used_api_placeholder
    meta = revised_prompt or ""
    if is_local_visual:
        desc = "Locally rendered slide preview (demo; not an AI image)."
        src_cat = "placeholder"
    elif meta == "pollinations":
        desc = "AI-generated slide image (Pollinations — free fallback when HF quota or keys unavailable)."
        src_cat = "pollinations"
    elif isinstance(meta, str) and meta.startswith("stock:"):
        desc = "Royalty-free stock photograph (web) matched to slide topic."
        src_cat = "stock"
    else:
        desc = "AI-generated slide illustration."
        src_cat = "generated"

    catalog_entry = {
        "image_id": image_id,
        "page": slide_index + 1,
        "caption": slide.get("slide_title", f"Slide {slide_index + 1}"),
        "description": desc,
        "asset_path": asset_path,
        "source": src_cat,
        "prompt": revised_prompt
        or _compose_topic_first_image_prompt(
            document_title,
            slide,
            image_style,
            slide_index=slide_index,
            deck_slide_count=deck_slide_count,
        ),
    }
    slide["image_refs"] = [image_id]
    counted = True
    return slide, catalog_entry, notes, counted


def attach_generated_images(
    document_id: str,
    document_title: str,
    slides: list[dict[str, Any]],
    image_catalog: list[dict[str, Any]],
    generate_images: bool,
    image_style: str,
    max_generated_images: int,
    fill_every_slide: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    notes: list[str] = []

    if not generate_images or max_generated_images <= 0:
        return slides, image_catalog, notes

    if _hf_only_enabled():
        ok_hf, hf_msg = slide_image_generation_status()
        if not ok_hf:
            if pillow_can_draw_slide_placeholders():
                notes.append(hf_msg)
                notes.append(
                    "HF-first prerequisites not met — drawing local PNG placeholders so each slide still has an image. "
                    "Unset SLIDE_IMAGE_HF_ONLY or add HF_TOKEN / fallback keys for AI images."
                )
            else:
                notes.append(hf_msg)
                notes.append(
                    "No slide images attached (HF-first mode misconfigured). "
                    "Unset SLIDE_IMAGE_HF_ONLY or add HF_TOKEN / fallback keys — or install Pillow for local previews."
                )
                return slides, image_catalog, notes
    else:
        available, status_message = slide_image_generation_status()
        if not available:
            if pillow_can_draw_slide_placeholders():
                notes.append(
                    f"{status_message} "
                    "Proceeding with local Pillow placeholders so every slide receives an image file."
                )
            else:
                notes.append(f"No AI slide images were added. {status_message}")
                return slides, image_catalog, notes

        if get_slide_image_provider() == "placeholder":
            notes.append(
                "IMAGE_MODE_LOCAL_ONLY: Slide pictures below are simple local drawings, NOT AI art. "
                "Add HF_TOKEN (Hugging Face), XAI_API_KEY, or OPENAI_API_KEY to your backend .env and restart Uvicorn "
                "to generate topic illustrations (e.g. photosynthesis leaves, chloroplasts) like a real image API."
            )

    generated_count = 0
    updated_catalog = list(image_catalog)
    updated_slides = [dict(slide) for slide in slides]
    # Never stop before every slide has been processed when filling the deck (cap must cover deck length).
    effective_cap = (
        max(max_generated_images, len(updated_slides))
        if fill_every_slide
        else max_generated_images
    )

    # Exactly one generated/stored asset per slide — never skip slides that reuse document figures.
    n_deck = len(updated_slides)
    slots = list(range(min(n_deck, effective_cap)))

    def _run_attachment(idx: int) -> tuple[int, dict[str, Any], dict[str, Any] | None, list[str], bool]:
        slide_out, cat_ent, loc_notes, counted = _generate_one_slide_attachment(
            document_id,
            document_title,
            updated_slides[idx],
            idx,
            len(updated_slides),
            image_style,
        )
        return idx, slide_out, cat_ent, loc_notes, counted

    batches: dict[int, tuple[dict[str, Any], dict[str, Any] | None, list[str], bool]] = {}
    if slots:
        workers = min(slide_image_parallel_workers(), len(slots))
        if workers <= 1:
            for idx in slots:
                _, slide_out, cat_ent, loc_notes, counted = _run_attachment(idx)
                batches[idx] = (slide_out, cat_ent, loc_notes, counted)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_run_attachment, idx) for idx in slots]
                for fut in concurrent.futures.as_completed(futures):
                    idx, slide_out, cat_ent, loc_notes, counted = fut.result()
                    batches[idx] = (slide_out, cat_ent, loc_notes, counted)

        for idx in sorted(batches.keys()):
            slide_out, cat_ent, loc_notes, counted = batches[idx]
            updated_slides[idx] = slide_out
            notes.extend(loc_notes)
            if cat_ent is not None:
                updated_catalog.append(cat_ent)
            if counted:
                generated_count += 1

    for idx in range(min(n_deck, effective_cap)):
        if teacher_slide_has_resolved_image(updated_slides[idx], updated_catalog):
            continue
        slide_out, cat_ent, loc_notes, counted = _generate_one_slide_attachment(
            document_id,
            document_title,
            updated_slides[idx],
            idx,
            len(updated_slides),
            image_style,
        )
        updated_slides[idx] = slide_out
        notes.extend(loc_notes)
        if cat_ent is not None:
            updated_catalog.append(cat_ent)
        if counted:
            generated_count += 1

    assert_teacher_slides_have_catalog_images(updated_slides, updated_catalog)

    label = active_image_model_label()
    if generated_count:
        provider = get_slide_image_provider()
        if provider == "placeholder":
            notes.append(
                f"Attached {generated_count} local slide illustration(s) for PPTX export ({label}; not AI-generated). "
                "Add HF_TOKEN / XAI_API_KEY / OPENAI_API_KEY for real image models."
            )
        elif provider == "huggingface":
            notes.append(f"Generated {generated_count} AI slide image(s) via Hugging Face ({label}).")
        elif provider == "xai":
            notes.append(f"Generated {generated_count} AI slide image(s) via xAI Grok Imagine ({label}).")
        else:
            notes.append(f"Generated {generated_count} AI slide image(s) via OpenAI ({label}).")
    else:
        notes.append(
            "No slide images were generated. Read the other notes in this list for API errors, "
            "or rely on local placeholders: unset image keys and keep SLIDE_IMAGE_NOAPI_PLACEHOLDERS=1 (default), "
            "or set SLIDE_IMAGE_PROVIDER=placeholder."
        )

    return updated_slides, updated_catalog, notes


def live_slide_image_data_url(
    document_title: str,
    slide: dict[str, Any],
    image_style: str,
    slide_index: int,
    warnings_out: list[str] | None = None,
    *,
    deck_slide_count: int | None = None,
) -> str:
    """Build a PNG data URL for browser embedding (HF first, then stock / backup AI; soft placeholder last)."""
    ensure_slide_image_prompt(slide, document_title)
    _sanitize_image_prompt(slide, document_title, image_style)

    try:
        raw, _ = _generate_single_image(
            slide,
            document_title,
            image_style,
            slide_index,
            deck_slide_count=deck_slide_count,
        )
    except Exception as exc:
        raw = None
        api_err = f"{exc.__class__.__name__}: {exc}"[:280]
    else:
        api_err = None

    if not raw:
        compact_lv = _compact_retry_prompt(document_title, slide, image_style)
        pol_b, _pol_m = _generate_pollinations_image(compact_lv, seed=slide_index * 19_999 + 5)
        if pol_b:
            raw = pol_b
    if not raw:
        raw, stock_meta = _fallback_stock_or_placeholder_bytes(
            slide, document_title, image_style, slide_index
        )
        if warnings_out is not None:
            if stock_meta and str(stock_meta).startswith("stock:"):
                src = str(stock_meta).split(":", 1)[-1]
                warnings_out.append(
                    f"Slide {slide_index + 1}: royalty-free stock photo ({src}) — AI paths returned no pixels."
                )
            else:
                detail = (
                    f" Slide error: {api_err}"
                    if api_err
                    else (
                        " HF, Pollinations, and Pexels/Unsplash (if keys set) returned nothing."
                    )
                )
                warnings_out.append(
                    f"Slide {slide_index + 1}: showing local PNG preview only.{detail} "
                    "HF quota (402) usually means top-up Hugging Face billing."
                )
    png = _coerce_png_bytes(raw)
    if len(png) < len(_FALLBACK_TINY_PNG):
        try:
            png = _generate_placeholder_image_bytes(slide, document_title, image_style, slide_index)
        except Exception:
            png = _distinct_fallback_png(slide_index)
    if len(png) < len(_FALLBACK_TINY_PNG):
        png = _distinct_fallback_png(slide_index)
    b64 = base64.standard_b64encode(png).decode("ascii")
    return f"data:image/png;base64,{b64}"
