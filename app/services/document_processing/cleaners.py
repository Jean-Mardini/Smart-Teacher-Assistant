import re
import unicodedata

# ---------------------------------------------------------------------------
# Arabic Presentation Forms range (U+FB50–U+FEFF).
# These appear when fitz extracts text from PDFs that store Arabic glyphs
# using isolated/initial/medial/final form codepoints instead of standard
# Arabic Unicode (U+0600–U+06FF).  NFKC normalization converts them back.
# ---------------------------------------------------------------------------
_PRES_FORMS_RE = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF]")


def clean_text(text: str) -> str:
    """Clean and normalise extracted text for EN / FR / AR and mixed documents.

    Steps applied in order:

    1. Bytes → str (UTF-8 with Latin-1 fallback).
    2. Normalise line endings (CRLF → LF, bare CR → LF).
    3. Collapse runs of spaces/tabs to a single space (preserves newlines).
    4. Remove non-printable control characters (keeps tab and newline).
    5. Remove excessive blank lines (3+ → 2).
    6. NFKC-normalise paragraphs that contain Arabic Presentation Forms.
       Unicode NFKC maps FB50–FEFF glyph codepoints back to the canonical
       Arabic letters in U+0600–U+06FF, restoring searchable logical-order text.
    """
    if not text:
        return ""

    # --- 1. Decode bytes -------------------------------------------------------
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            text = text.decode("latin-1")

    # --- 2. Normalise line endings ---------------------------------------------
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\r", "\n", text)

    # --- 3. Collapse whitespace (spaces/tabs only) -----------------------------
    text = re.sub(r"[ \t]+", " ", text)

    # --- 4. Strip non-printable control characters ----------------------------
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

    # --- 5. Collapse excessive blank lines ------------------------------------
    text = re.sub(r"\n{3,}", "\n\n", text)

    # --- 6. Normalise Arabic Presentation Forms --------------------------------
    # Only touch paragraphs that actually contain presentation-form codepoints.
    # NFKC is safe on Latin/French text (no-op) so we could apply it globally,
    # but limiting it avoids any unexpected changes to non-Arabic content.
    lines = text.split("\n")
    normalised = [
        unicodedata.normalize("NFKC", line) if _PRES_FORMS_RE.search(line) else line
        for line in lines
    ]

    return "\n".join(normalised).strip()
