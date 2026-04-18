import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Compiled patterns for text-only heading detection
# ---------------------------------------------------------------------------

# Numbered heading: "1.", "1.1", "2.3.4" followed by a letter
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)[.)]\s+[A-Za-z\u0600-\u06FF]")

# Roman numeral headings: "I.", "IV.", "XII."
_ROMAN = re.compile(r"^[IVXLCDM]{1,6}\.\s+[A-Za-z]")

# Explicit section/chapter keywords — EN, FR, AR
_SECTION_KEYWORDS = re.compile(
    r"^(chapter|section|part|chapitre|partie|annexe|appendix|abstract"
    r"|introduction|conclusion|references|bibliography"
    r"|الملخص|المقدمة|المنهجية|المنهج|النتائج|الخاتمة|المراجع|الفصل|القسم"
    r"|المناقشة|التوصيات|الأهداف)\b",
    re.IGNORECASE,
)

# Font size thresholds (ratio of line's font size to document body size)
_H1_RATIO = 1.35   # 35 % larger than body → h1
_H2_RATIO = 1.15   # 15 % larger            → h2
_H2_BOLD_RATIO = 1.05  # bold + 5 % larger  → h2
_H3_RATIO = 1.05   # 5 % larger             → h3


# ---------------------------------------------------------------------------
# Font-size helpers
# ---------------------------------------------------------------------------

def _compute_body_size(sizes: List[float]) -> float:
    """Return the document's body font size (most frequent non-outlier size).

    Sizes < 6 pt (invisible) and > 40 pt (display/title outliers) are excluded
    from the computation so they don't skew the mode.
    """
    filtered = [round(s, 1) for s in sizes if 6.0 <= s <= 40.0]
    if not filtered:
        return 12.0
    return Counter(filtered).most_common(1)[0][0]


def _font_heading_level(
    size: float,
    bold: bool,
    body_size: float,
    line: str,
) -> int:
    """Return heading level (1–3) derived from font size and bold flag, or 0.

    Rules (evaluated in priority order):
    - ratio >= 1.35                               → h1
    - ratio >= 1.15  OR  (bold AND ratio >= 1.05) → h2
    - ratio >= 1.05                               → h3
    - bold + short (≤10 words) + mostly title-case → h3
    """
    ratio = size / body_size if body_size > 0.0 else 1.0
    words = line.split()
    n = len(words)

    if ratio >= _H1_RATIO:
        return 1
    if ratio >= _H2_RATIO or (bold and ratio >= _H2_BOLD_RATIO):
        return 2
    if ratio >= _H3_RATIO:
        return 3
    # Bold + short + mostly title-case is a conservative h3 signal
    if bold and 1 <= n <= 10:
        cap = sum(1 for w in words if w and w[0].isupper())
        if cap / n >= 0.6:
            return 3
    return 0


# ---------------------------------------------------------------------------
# Text-only heading heuristics
# ---------------------------------------------------------------------------

def _text_heading_level(line: str) -> int:
    """Return heading level (1–3) from text content alone, or 0.

    Signals checked (in priority order):
    1. ALL CAPS short line              → h1
    2. Roman numeral prefix             → h1
    3. Section keyword at start         → h1
    4. Numbered prefix (1. / 1.1 / …)  → h2 or h3 by depth
    5. Mostly title-case, 3–10 words    → h2
    """
    if not line:
        return 0

    line = line.strip()
    if len(line) > 120:
        return 0

    words = line.split()
    if not words:
        return 0

    # --- 1. ALL CAPS (1–12 words, no repeated-char artifacts like "IIIIII") ---
    if line.isupper() and 1 <= len(words) <= 12:
        if not re.search(r"(.)\1{2,}", line):
            return 1

    # --- 2. Roman numeral heading ---
    if _ROMAN.match(line):
        return 1

    # --- 3. Section keyword ---
    if _SECTION_KEYWORDS.match(line) and len(words) <= 10:
        return 1

    # --- 4. Numbered heading ---
    m = _NUMBERED.match(line)
    if m:
        depth = m.group(1).count(".") + 1  # "1" → 1, "1.1" → 2, "1.1.1" → 3
        return min(depth + 1, 3)            # depth 1 → h2, depth 2+ → h3

    # --- 5. Title-case (3–10 words) —- guard against location strings & data rows ---
    if 3 <= len(words) <= 10:
        if re.search(r"^[A-Z][a-zA-Z]+,\s+[A-Z][a-zA-Z]+$", line):
            return 0
        if all(re.match(r"^[\d%.,]+$", w) for w in words):
            return 0
        cap = sum(1 for w in words if w and w[0].isupper())
        if cap / len(words) > 0.6:
            return 2

    return 0


# ---------------------------------------------------------------------------
# Combined heading level
# ---------------------------------------------------------------------------

def _heading_level(
    line: str,
    size: Optional[float] = None,
    bold: bool = False,
    body_size: float = 12.0,
) -> int:
    """Return heading level (1–3) using all available signals, or 0.

    When font metadata (size, bold) is provided, font-based detection is
    combined with text heuristics and the higher level wins.  This lets a
    numbered heading that happens to be body-sized still be found, and lets a
    large/bold line that doesn't match a text pattern still be promoted.
    """
    text_level = _text_heading_level(line)
    if size is None:
        return text_level
    font_level = _font_heading_level(size, bold, body_size, line)
    return max(text_level, font_level)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def split_into_sections(
    full_text: str,
    pages: List[Dict[str, Any]] = None,
    line_meta: List[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Split document text into structured sections.

    Parameters
    ----------
    full_text:
        The complete document text (lines separated by ``\\n``).
    pages:
        Optional list of ``{"page": N, "text": "..."}`` dicts used to map
        lines back to their source page numbers.
    line_meta:
        Optional list of ``{"text": str, "size": float, "bold": bool,
        "page": int}`` dicts produced by PyMuPDF span extraction.  When
        provided, font size and bold flag are used alongside text heuristics
        for richer heading detection.  The first occurrence of each unique
        text string is used (case-sensitive, stripped).

    Returns
    -------
    List of section dicts with keys:
        section_id, heading, level, page_start, page_end, text
    """

    # --- Build line → page lookup from pages list --------------------------
    line_to_page: Dict[str, int] = {}
    if pages:
        for entry in pages:
            page_num = entry.get("page", 1)
            for raw in entry.get("text", "").split("\n"):
                key = raw.strip()
                if key and key not in line_to_page:
                    line_to_page[key] = page_num

    # --- Build line → font-meta lookup from line_meta ----------------------
    # Dict: stripped text → (size, bold, page)
    meta_lookup: Dict[str, Tuple[float, bool, int]] = {}
    body_size = 12.0

    if line_meta:
        all_sizes: List[float] = []
        for item in line_meta:
            key = item.get("text", "").strip()
            size = float(item.get("size", 12.0))
            bold = bool(item.get("bold", False))
            page = int(item.get("page", 1))
            if key and key not in meta_lookup:
                meta_lookup[key] = (size, bold, page)
            all_sizes.append(size)
        body_size = _compute_body_size(all_sizes)

    # --- Section splitting -------------------------------------------------
    lines = full_text.split("\n")
    sections: List[Dict[str, Any]] = []

    current_heading = "Document Start"
    current_level = 1
    current_page_start = 1
    current_content: List[str] = []

    def _flush(next_page: int) -> None:
        nonlocal current_heading, current_level, current_page_start, current_content
        if current_content:
            sections.append(
                {
                    "section_id": f"sec_{len(sections) + 1}",
                    "heading": current_heading,
                    "level": current_level,
                    "page_start": current_page_start,
                    "page_end": next_page if next_page != current_page_start else None,
                    "text": "\n".join(current_content).strip(),
                }
            )
        current_content = []

    for raw_line in lines:
        clean = raw_line.strip()
        if not clean:
            continue

        # Resolve page number (font meta takes priority over pages list)
        if clean in meta_lookup:
            size, bold, meta_page = meta_lookup[clean]
            current_page = meta_page
            level = _heading_level(clean, size=size, bold=bold, body_size=body_size)
        else:
            current_page = line_to_page.get(clean, current_page_start)
            level = _heading_level(clean)  # text-only

        if level > 0:
            _flush(current_page)
            current_heading = clean
            current_level = level
            current_page_start = current_page
        else:
            current_content.append(clean)

    _flush(current_page_start)

    return sections
