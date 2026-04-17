import logging
import os
import re
import fitz
import pdfplumber
import pytesseract
from PIL import Image
from collections import Counter, defaultdict
from .cleaners import clean_text

logger = logging.getLogger(__name__)

_CAPTION_RE = re.compile(
    r"\b(figure|fig\.?|image|photo|illustration)\s*[.:–\-]?\s*\d*",
    re.IGNORECASE,
)

# Covers all standard Arabic blocks including Presentation Forms (FB50-FEFF).
# Presentation Forms appear when fitz extracts glyphs from PDFs that use
# isolated/final/medial form codepoints instead of canonical Arabic letters.
_ARABIC_RANGE = re.compile(
    r'[\u0600-\u06FF'   # Arabic (main block)
    r'\u0750-\u077F'    # Arabic Supplement
    r'\u08A0-\u08FF'    # Arabic Extended-A
    r'\uFB50-\uFDFF'    # Arabic Presentation Forms-A
    r'\uFE70-\uFEFF]'   # Arabic Presentation Forms-B
)

# Threshold: paragraphs with this many presentation-form chars need pdfplumber.
_PRES_FORMS_RE = re.compile(r'[\uFB50-\uFDFF\uFE70-\uFEFF]')


def _has_pres_forms(text: str, threshold: int = 5) -> bool:
    """Return True if *text* contains enough Arabic Presentation Form characters
    to indicate a fitz font-encoding failure.  pdfplumber handles these correctly.
    """
    return len(_PRES_FORMS_RE.findall(text)) >= threshold


def _remove_headers_footers(pages: list) -> list:
    """
    Remove lines that appear verbatim in 30%+ of pages (headers/footers).
    Only considers short lines (< 120 chars).
    """
    if len(pages) < 3:
        return pages

    threshold = max(2, int(len(pages) * 0.30))

    # Count how many pages each short line appears on
    line_counts = Counter()
    for page in pages:
        seen_on_this_page = set()
        for line in page["text"].split("\n"):
            line = line.strip()
            if line and len(line) < 120:
                if line not in seen_on_this_page:
                    line_counts[line] += 1
                    seen_on_this_page.add(line)

    repeated = {line for line, count in line_counts.items() if count >= threshold}

    if not repeated:
        return pages

    cleaned_pages = []
    for page in pages:
        filtered = "\n".join(
            line for line in page["text"].split("\n")
            if line.strip() not in repeated
        )
        cleaned_pages.append({"page": page["page"], "text": filtered.strip()})

    return cleaned_pages


def _extract_with_pdfplumber(filepath: str) -> list:
    """
    Fallback extractor using pdfplumber.
    Better for multi-column layouts.
    """
    pages = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            cleaned = clean_text(text)
            pages.append({"page": page.page_number, "text": cleaned})
    return pages


def _looks_garbled(text: str) -> bool:
    """
    Detect garbled text from two causes:
    1. Multi-column layout: fitz joins columns → very long words (avg length > 20)
    2. Font encoding failure: Arabic chars mapped to wrong Unicode → one char repeats
       heavily (e.g. the whole page becomes "I I I I I I")
    """
    words = text.split()
    if not words:
        return False

    # Multi-column check
    avg_len = sum(len(w) for w in words) / len(words)
    if avg_len > 20:
        return True

    # Repeated-character encoding check.
    # Exclude geometric/box shapes (■ □ U+2500-U+25FF) — these are valid PDF
    # font-substitution placeholders, not encoding errors.
    stripped = [c for c in text if not c.isspace() and not (0x2500 <= ord(c) <= 0x25FF)]
    if len(stripped) >= 15:
        most_common_freq = Counter(stripped).most_common(1)[0][1] / len(stripped)
        if most_common_freq > 0.35:
            return True

    return False


def _extract_page_rtl(page) -> str:
    """
    Extract text from an Arabic (RTL) page using word-level position sorting.

    fitz returns Arabic words in visual left-to-right order, which is reversed
    relative to the actual reading order. This function:
      1. Gets all words with their bounding boxes
      2. Groups them into lines by vertical position
      3. Within each line, sorts words by x descending (rightmost = first word in Arabic)
    """
    words = page.get_text("words")  # (x0, y0, x1, y1, "word", block_no, line_no, word_no)
    if not words:
        return ""

    line_groups = defaultdict(list)
    for w in words:
        # Snap y to nearest 4 units so words on the same line cluster together
        line_key = round(w[1] / 4) * 4
        line_groups[line_key].append(w)

    result_lines = []
    for y in sorted(line_groups.keys()):
        # Build the line in LTR order first to inspect its content
        ltr_words = sorted(line_groups[y], key=lambda w: w[0])
        line_text = " ".join(w[4] for w in ltr_words)

        # Only reverse word order for lines that actually contain Arabic characters.
        # English/French lines inside an Arabic document stay LTR.
        if _ARABIC_RANGE.search(line_text):
            # Step 1: reverse word ORDER within the line (RTL reading direction)
            rtl_words = sorted(line_groups[y], key=lambda w: -w[0])

            # Step 2: reverse CHARACTER ORDER within each Arabic word.
            # Arabic PDFs often store characters in visual (LTR) order, so
            # "الملخص" is stored as "صخلملا". Reversing the characters fixes this.
            fixed = []
            for w in rtl_words:
                word = w[4]
                fixed.append(word[::-1] if _ARABIC_RANGE.search(word) else word)

            result_lines.append(" ".join(fixed))
        else:
            result_lines.append(line_text)

    return "\n".join(result_lines)


def extract_pdf_text(filepath: str):
    """Extract text from a PDF.

    Per-page strategy (in priority order):
    1. fitz  — fast, accurate for single-column text.
    2. pdfplumber — fallback when fitz output is garbled (multi-column layout)
       OR contains Arabic Presentation Forms (font-encoding failure).
       pdfplumber correctly extracts both layouts and Arabic encoding.
    3. pytesseract OCR — last resort for scanned / image-only pages.

    After extraction, repeated headers/footers are stripped.

    Returns:
        pages:     list of {"page": N, "text": "..."}
        full_text: complete cleaned text
    """
    try:
        doc = fitz.open(filepath)
    except Exception as e:
        raise ValueError(f"Cannot open PDF '{filepath}': {e}")

    if doc.is_encrypted:
        doc.close()
        raise ValueError(f"PDF '{filepath}' is password-protected.")

    pages = []
    ocr_attempted = False

    # Open pdfplumber once alongside fitz so it can be used as a per-page
    # fallback without repeatedly re-opening the file.
    with pdfplumber.open(filepath) as plumber_doc:
        for page_number, page in enumerate(doc, start=1):
            plumber_page = plumber_doc.pages[page_number - 1]

            text = page.get_text("text")

            # --- OCR fallback for blank / scanned pages ----------------------
            if not text.strip():
                ocr_attempted = True
                try:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    text = pytesseract.image_to_string(img)
                except Exception as ocr_err:
                    logger.warning("OCR failed for page %d: %s", page_number, ocr_err)
                    text = ""

            cleaned = clean_text(text)

            # --- pdfplumber fallback -----------------------------------------
            # Triggered by:
            #   • _looks_garbled  : multi-column layout or heavy encoding noise
            #   • _has_pres_forms : Arabic Presentation Forms from fitz font map
            # pdfplumber is tried first because it is faster than OCR and handles
            # both cases well.  OCR is only used if pdfplumber also fails.
            if _looks_garbled(cleaned) or _has_pres_forms(cleaned):
                plumber_text = (
                    plumber_page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                )
                if plumber_text.strip():
                    plumber_cleaned = clean_text(plumber_text)
                    if not _looks_garbled(plumber_cleaned):
                        pages.append({"page": page_number, "text": plumber_cleaned})
                        continue  # pdfplumber succeeded — skip further fallbacks

                # pdfplumber also failed → OCR as last resort
                ocr_attempted = True
                try:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    try:
                        ocr_text = pytesseract.image_to_string(img, lang="ara+eng+fra")
                    except pytesseract.TesseractError:
                        ocr_text = pytesseract.image_to_string(img)
                    if ocr_text.strip():
                        cleaned = clean_text(ocr_text)
                except Exception:
                    pass  # keep fitz result if everything fails

            # --- RTL word-order fix for standard Arabic ----------------------
            # Triggered only when fitz output contains standard Arabic
            # codepoints (U+0600-06FF) — presentation-form pages are handled
            # above by the pdfplumber branch and never reach here.
            elif _ARABIC_RANGE.search(cleaned):
                rtl_text = _extract_page_rtl(page)
                if rtl_text.strip():
                    cleaned = clean_text(rtl_text)

            pages.append({"page": page_number, "text": cleaned})

    doc.close()

    pages = _remove_headers_footers(pages)
    full_text = "\n".join(p["text"] for p in pages)
    return pages, full_text, ocr_attempted


def _pdf_image_caption(page, xref: int) -> str:
    """Return a caption for an image by checking text immediately below or above it.

    Checks a 60pt strip below first (most common placement), then a 40pt strip
    above. Only returns text that matches an explicit Figure/Image pattern.
    """
    for info in page.get_image_info():
        if info.get("xref") != xref:
            continue
        x0, y0, x1, y1 = info["bbox"]
        w, h = float(page.rect.width), float(page.rect.height)

        below = page.get_text("text", clip=fitz.Rect(0, y1, w, min(h, y1 + 60))).strip()
        if below and _CAPTION_RE.search(below):
            return below.split("\n")[0].strip()

        above = page.get_text("text", clip=fitz.Rect(0, max(0.0, y0 - 40), w, y0)).strip()
        if above and _CAPTION_RE.search(above):
            return above.split("\n")[-1].strip()

        break
    return ""


def extract_pdf_images(filepath: str, document_id: str = "doc") -> list:
    """Extract images from a PDF and save them to disk.

    Skips images smaller than 50x50 px (icons, decorations) and deduplicates
    by xref so the same image embedded on multiple pages is only saved once.

    Returns a list of {"image_id", "page", "caption", "path"} dicts.
    """
    results = []
    img_dir = os.path.join("outputs", "images", document_id)
    counter = 0
    seen_xrefs: set = set()

    try:
        doc = fitz.open(filepath)
        for page_num, page in enumerate(doc, start=1):
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                try:
                    base_image = doc.extract_image(xref)
                    if base_image["width"] < 50 or base_image["height"] < 50:
                        continue

                    counter += 1
                    img_id = f"img_{counter}"
                    os.makedirs(img_dir, exist_ok=True)
                    ext = base_image.get("ext", "png")
                    img_path = os.path.join(img_dir, f"{img_id}.{ext}")
                    with open(img_path, "wb") as f:
                        f.write(base_image["image"])

                    caption = _pdf_image_caption(page, xref) or f"Figure {counter}"
                    results.append({
                        "image_id": img_id,
                        "page": page_num,
                        "caption": caption,
                        "path": img_path,
                    })
                except Exception:
                    continue
        doc.close()
    except Exception as exc:
        logger.warning("Image extraction skipped for %s: %s", filepath, exc)

    return results
