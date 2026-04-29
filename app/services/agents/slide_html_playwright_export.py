"""Gamma-style PPTX: HTML/CSS slides → Playwright PNG → python-pptx full-bleed assembly."""

from __future__ import annotations

import base64
import logging
import html as html_module
import os
import re
from io import BytesIO
from typing import Any

from app.services.agents.image_slide_pptx_export import build_pptx_full_bleed_images

_logger = logging.getLogger(__name__)

_LW = 1280
_LH = 720
_XW = 1920
_XH = 1080
_SCALE = _XW / _LW


def _px(n: float) -> int:
    return int(round(n * _SCALE))


def _decode_data_url_to_bytes(s: str) -> bytes | None:
    if not s or "base64," not in s.lower():
        return None
    try:
        b64 = s.split("base64,", 1)[1].strip().replace("\n", "").replace("\r", "")
        pad = "=" * ((4 - len(b64) % 4) % 4)
        return base64.standard_b64decode(b64 + pad)
    except Exception:
        return None


def _png_ihdr_dims(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24:
        return None
    sig = (0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
    if any(data[i] != sig[i] for i in range(8)):
        return None
    w = (data[16] << 24) | (data[17] << 16) | (data[18] << 8) | data[19]
    h = (data[20] << 24) | (data[21] << 16) | (data[22] << 8) | data[23]
    if 1 <= w < 1_000_000 and 1 <= h < 1_000_000:
        return (w, h)
    return None


def should_show_slide_image_export(src: str) -> bool:
    raw = _decode_data_url_to_bytes(src)
    if not raw:
        return False
    png_sig = len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n"
    if png_sig:
        dims = _png_ihdr_dims(raw)
        if dims and dims[0] <= 96 and dims[1] <= 96:
            return False
        if len(raw) < 140:
            return False
        return True
    return len(raw) >= 200


_BOLD_SPLIT = re.compile(r"(\*\*[^*]+\*\*)")


def _fmt_inline(s: str) -> str:
    parts = _BOLD_SPLIT.split(str(s))
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if p.startswith("**") and p.endswith("**") and len(p) > 4:
            out.append(f"<strong>{html_module.escape(p[2:-2])}</strong>")
        else:
            out.append(html_module.escape(p))
    return "".join(out)


def _bullets_ul(items: list[str], *, fs: int = 17) -> str:
    lis = "".join(
        f'<li style="margin:0 0 {_px(10)}px 0;line-height:1.45;">{_fmt_inline(x)}</li>' for x in items if str(x).strip()
    )
    return f'<ul style="margin:0;padding-left:{_px(18)}px;color:#334155;font-size:{fs}px;">{lis}</ul>'


def _title_block(title: str, slide_index: int, *, centered: bool = False) -> str:
    """Title row. Static HTML cannot render Lucide icons; mirror the live UI by prefixing the title.

    First slide (index 0): title only. From the second slide: ``1- Title``, ``2- Title``, … (space after hyphen).
    """
    if slide_index >= 1:
        esc = html_module.escape(f"{slide_index}- ") + _fmt_inline(title)
    else:
        esc = _fmt_inline(title)
    jc = "center" if centered else "flex-start"
    ta = "center" if centered else "left"
    fs = _px(34)
    return f"""
<div style="display:flex;align-items:center;gap:{_px(14)}px;width:100%;justify-content:{jc};margin-bottom:{_px(20)}px;min-width:0;">
  <h2 style="margin:0;font-size:{fs}px;font-weight:700;color:#0f172a;letter-spacing:-0.02em;line-height:1.15;text-align:{ta};flex:1;">{esc}</h2>
</div>"""


def _card_html(inner: str, *, bg: str = "#eef3f8", mw: str | None = None) -> str:
    mw_css = f"max-width:{mw};" if mw else f"max-width:{_px(420)}px;"
    return f"""
<div style="padding:{_px(20)}px;border-radius:{_px(20)}px;background:{bg};border:1px solid rgba(148,163,184,0.35);box-sizing:border-box;box-shadow:0 {_px(8)}px {_px(20)}px rgba(0,0,0,0.05);text-align:left;align-self:start;width:100%;{mw_css}">
  {inner}
</div>"""


def _slide_shell(inner: str) -> str:
    return f"""
<div class="slide-root" style="width:{_LW}px;min-height:{_LH}px;height:auto;box-sizing:border-box;background:linear-gradient(135deg,#e6eef7 0%,#cfdceb 100%);border-radius:{_px(30)}px;box-shadow:0 {_px(20)}px {_px(44)}px rgba(15,23,42,0.09);overflow:hidden;display:flex;flex-direction:column;padding:{_px(40)}px;gap:{_px(22)}px;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;">
  {inner}
</div>"""


def _img_tag(src: str, *, compact: bool = False) -> str:
    if not should_show_slide_image_export(src):
        return ""
    h = _px(200) if compact else _px(380)
    return (
        f'<img src="{html_module.escape(src, quote=True)}" alt="" draggable="false" '
        f'style="width:100%;height:{h}px;object-fit:cover;border-radius:{_px(12)}px;background:#f1f5f9;display:block;" />'
    )


def _layout_centered_cards(title: str, bullets: list[str], slide_index: int) -> str:
    """Body-centered three-column grid (``split_3_columns``)."""
    third = max(1, (len(bullets) + 2) // 3)
    chunks = [
        bullets[0:third],
        bullets[third : third * 2],
        bullets[third * 2 : third * 3],
    ]
    grid_cols = "repeat(3, minmax(0, 280px))"
    cards = ""
    for i in range(3):
        chunk = chunks[i] if i < len(chunks) else []
        body = "".join(
            f'<p style="margin:{_px(8)}px 0 0 0;color:#334155;font-size:{_px(17)}px;">{_fmt_inline(b)}</p>' for b in chunk
        )
        cards += _card_html(body if body.strip() else f'<p style="color:#94a3b8;font-size:{_px(14)}px;">&nbsp;</p>')
    inner = f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;width:100%;text-align:center;">
  {_title_block(title, slide_index, centered=True)}
  <div style="display:grid;grid-template-columns:{grid_cols};gap:{_px(20)}px;width:100%;justify-content:center;justify-items:center;align-items:start;">
    {cards}
  </div>
</div>"""
    return _slide_shell(inner)


def _layout_split_left_right(title: str, bullets: list[str], img: str, slide_index: int, *, img_first: bool) -> str:
    show = should_show_slide_image_export(img)
    col_img = f'<div style="flex:0 0 54%;min-width:0;">{_img_tag(img)}</div>'
    col_txt = f"""
<div style="flex:1;display:flex;flex-direction:column;gap:{_px(14)}px;min-width:0;">
  {_title_block(title, slide_index, centered=False)}
  {_bullets_ul(bullets)}
</div>"""
    if not show:
        inner = f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;width:100%;">
  {_title_block(title, slide_index, centered=True)}
  <div style="max-width:{_px(920)}px;text-align:left;width:100%;">{_bullets_ul(bullets)}</div>
</div>"""
        return _slide_shell(inner)
    row = f'<div style="display:flex;flex:1;gap:{_px(28)}px;align-items:flex-start;width:100%;">{col_img + col_txt if img_first else col_txt + col_img}</div>'
    return _slide_shell(row)


def live_slide_fragment(spec: dict[str, Any], slide_index: int = 0) -> str:
    """Inner HTML for one slide (1280-logical canvas). ``slide_index`` drives the title badge (see ``_title_block``)."""
    layout = str(spec.get("layout") or spec.get("type") or "split_left").lower()
    title = str(spec.get("title") or "Slide").strip() or "Slide"
    bullets = list(spec.get("bullets") or [])
    img = str(spec.get("image") or "")

    if layout == "split_right":
        return _layout_split_left_right(title, bullets, img, slide_index, img_first=False)
    if layout in ("split_left", "feature", "highlight"):
        return _layout_split_left_right(title, bullets, img, slide_index, img_first=True)

    if layout == "split_3_columns":
        return _layout_centered_cards(title, bullets, slide_index)

    if layout == "grid_cards_3":
        chunks = bullets[:9]
        cards = ""
        for b in chunks:
            cards += _card_html(f'<p style="margin:0;color:#334155;font-size:{_px(16)}px;">{_fmt_inline(b)}</p>')
        inner = f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;width:100%;">
  {_title_block(title, slide_index, centered=True)}
  <div style="display:grid;grid-template-columns:repeat(3, minmax(0, 280px));gap:{_px(20)}px;width:100%;justify-content:center;justify-items:center;">
    {cards}
  </div>
  {_f_optional_footer_img(img)}
</div>"""
        return _slide_shell(inner)

    if layout == "grid_cards_2x2":
        cards = ""
        for b in bullets[:4]:
            cards += _card_html(f'<p style="margin:0;color:#334155;font-size:{_px(15)}px;">{_fmt_inline(b)}</p>')
        inner = f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;width:100%;">
  {_title_block(title, slide_index, centered=True)}
  <div style="display:grid;grid-template-columns:repeat(2, minmax(0, 280px));gap:{_px(20)}px;width:100%;justify-content:center;">
    {cards}
  </div>
  {_f_optional_footer_img(img)}
</div>"""
        return _slide_shell(inner)

    if layout in ("text_comparison", "title_top_2_columns"):
        mid = max(1, (len(bullets) + 1) // 2)
        left, right = bullets[:mid], bullets[mid:]
        inner = f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;width:100%;">
  {_title_block(title, slide_index, centered=True)}
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:{_px(20)}px;width:100%;max-width:{_px(960)}px;justify-items:center;align-items:start;">
    {_card_html(_bullets_ul(left))}
    {_card_html(_bullets_ul(right))}
  </div>
</div>"""
        return _slide_shell(inner)

    if layout == "comparison":
        mid = max(1, (len(bullets) + 1) // 2)
        left, right = bullets[:mid], bullets[mid:]
        hero = f'<div style="width:100%;max-width:{_px(720)}px;margin:0 auto {_px(16)}px;">{_img_tag(img)}</div>' if should_show_slide_image_export(img) else ""
        inner = f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;width:100%;">
  {hero}
  {_title_block(title, slide_index, centered=True)}
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:{_px(20)}px;width:100%;max-width:{_px(920)}px;">
    {_card_html(_bullets_ul(left), bg="#eef3f8")}
    {_card_html(_bullets_ul(right), bg="#fffbeb")}
  </div>
</div>"""
        return _slide_shell(inner)

    if layout == "grid":
        parts = bullets[:4]
        while len(parts) < 4:
            parts.append("")
        pairs = [(parts[0], parts[1]), (parts[2], parts[3])]
        hero = (
            f'<div style="width:100%;max-width:{_px(880)}px;margin:0 auto {_px(18)}px;">{_img_tag(img)}</div>'
            if should_show_slide_image_export(img)
            else ""
        )
        cells = ""
        for pair in pairs:
            body = "".join(
                f'<p style="margin:{_px(10)}px 0 0 0;color:#334155;font-size:{_px(16)}px;">{_fmt_inline(x)}</p>'
                for x in pair
                if str(x).strip()
            )
            cells += _card_html(body or f'<p style="color:#94a3b8">{html_module.escape("—")}</p>')
        inner = f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;width:100%;">
  {_title_block(title, slide_index, centered=True)}
  {hero}
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:{_px(20)}px;width:100%;max-width:{_px(920)}px;justify-items:center;">
    {cells}
  </div>
</div>"""
        return _slide_shell(inner)

    if layout in ("top_bottom", "image_top_text_bottom"):
        hero = (
            f'<div style="width:100%;max-width:{_px(920)}px;margin:0 auto {_px(16)}px;">{_img_tag(img)}</div>'
            if should_show_slide_image_export(img)
            else ""
        )
        inner = f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;width:100%;">
  {_title_block(title, slide_index, centered=True)}
  {hero}
  {_card_html(_bullets_ul(bullets), mw=f"{_px(880)}px")}
</div>"""
        return _slide_shell(inner)

    if layout in ("text_only", "text_only_centered"):
        # Matches React ``LiveSlideDeck`` text_only: centered title + single bullet block (no tall 2-col PPT artifact).
        inner = f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;width:100%;box-sizing:border-box;">
  <div style="max-width:{_px(880)}px;width:100%;">
    {_title_block(title, slide_index, centered=True)}
    {_bullets_ul(bullets)}
  </div>
</div>"""
        return _slide_shell(inner)

    # Default: hero split left
    return _layout_split_left_right(title, bullets, img, slide_index, img_first=True)


def _f_optional_footer_img(img: str) -> str:
    if not should_show_slide_image_export(img):
        return ""
    return f'<div style="margin-top:{_px(18)}px;width:{_px(220)}px;max-width:100%;">{_img_tag(img, compact=True)}</div>'


def live_slide_to_full_html(spec: dict[str, Any], slide_index: int = 0) -> str:
    """Standalone HTML document with viewport wrapper → 1920×1080 PNG via scale."""
    frag = live_slide_fragment(spec, slide_index)
    scale = _XW / _LW
    # Scale slide from 1280-wide design to fill 1920×1080 (same as CSS transform in browser preview scaling).
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width={_XW}, height={_XH}"/>
<style>
html,body{{margin:0;padding:0;background:#b8c5d6;}}
/* Fixed 16:9 frame; slide is centered — short decks must not sit under a giant empty band (matches live preview balance). */
#vp{{width:{_XW}px;height:{_XH}px;overflow:hidden;position:relative;background:linear-gradient(180deg,#dbeafe 0%,#e2e8f0 100%);}}
#stage{{
  position:absolute;
  left:50%;
  top:50%;
  width:{_LW}px;
  transform:translate(-50%,-50%) scale({scale});
  transform-origin:center center;
}}
</style></head><body>
<div id="vp"><div id="stage">{frag}</div></div>
</body></html>"""


def _fit_image_to_16_9(png_bytes: bytes) -> bytes:
    from PIL import Image

    src = Image.open(BytesIO(png_bytes)).convert("RGB")
    sw, sh = src.size
    tw, th = _XW, _XH
    sc = min(tw / sw, th / sh)
    nw, nh = max(1, int(sw * sc)), max(1, int(sh * sc))
    try:
        _rs = Image.Resampling.LANCZOS
    except AttributeError:
        _rs = Image.LANCZOS  # Pillow < 9
    src = src.resize((nw, nh), _rs)
    out = Image.new("RGB", (tw, th), (230, 238, 247))
    out.paste(src, ((tw - nw) // 2, (th - nh) // 2))
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_slide_png_bytes(html: str) -> bytes:
    """Headless Chromium screenshot → PNG bytes fitted to {_XW}×{_XH}."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": _XW, "height": _XH})
        page.set_content(html, wait_until="load")
        raw = page.screenshot(type="png", full_page=False)
        browser.close()
    return _fit_image_to_16_9(raw)


def build_pptx_via_html_playwright(slides: list[dict[str, Any]]) -> bytes:
    """Render each slide HTML → PNG (Playwright) → single-aspect PPTX."""
    urls: list[str] = []
    for i, spec in enumerate(slides):
        html = live_slide_to_full_html(spec, i)
        png_bytes = render_slide_png_bytes(html)
        b64 = base64.standard_b64encode(png_bytes).decode("ascii")
        urls.append(f"data:image/png;base64,{b64}")
    return build_pptx_full_bleed_images(urls)


def html_export_available() -> bool:
    try:
        from importlib.util import find_spec

        return find_spec("playwright") is not None
    except Exception:
        return False


def want_html_export() -> bool:
    return os.getenv("SLIDE_EXPORT_HTML", "1").strip().lower() not in ("0", "false", "no", "off")


def build_pptx_live_auto(slides: list[dict[str, Any]]) -> tuple[bytes, str]:
    """Prefer HTML/Playwright; fall back to legacy python-pptx builder."""
    from app.services.agents.modern_gamma_slide_system import build_ppt_from_live_slides

    if want_html_export() and html_export_available():
        try:
            return build_pptx_via_html_playwright(slides), "html_playwright"
        except Exception as exc:
            _logger.warning("HTML/Playwright PPTX export failed; falling back to python-pptx: %s", exc)
    return build_ppt_from_live_slides(slides), "python_pptx_legacy"
