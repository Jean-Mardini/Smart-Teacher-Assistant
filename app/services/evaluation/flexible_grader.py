import io
import json
import os
import re
import zipfile
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from docx import Document

from app.storage.files import get_evaluation_dir
from openai import OpenAI
from pypdf import PdfReader
from pptx import Presentation

APP_TITLE = "Flexible Grader"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
UPLOAD_TYPES = ["pdf", "docx", "pptx", "txt", "md", "json", "csv", "html", "rtf"]


def config_path() -> str:
    return str(get_evaluation_dir() / "config.json")


def presets_path() -> str:
    return str(get_evaluation_dir() / "rubric_presets.json")


def history_path() -> str:
    return str(get_evaluation_dir() / "history.jsonl")


# =========================================================
# Storage
# =========================================================
def safe_read_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def safe_write_json(path: str, data: Dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def append_history(record: Dict[str, Any]) -> None:
    try:
        with open(history_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def load_history(limit: int = 100) -> List[Dict[str, Any]]:
    hp = history_path()
    if not os.path.exists(hp):
        return []
    rows = []
    try:
        with open(hp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    rows.reverse()
    return rows[:limit]


def clear_history() -> None:
    try:
        hp = history_path()
        if os.path.exists(hp):
            os.remove(hp)
    except Exception:
        pass


def load_config() -> Dict[str, Any]:
    return safe_read_json(config_path())


def save_config(cfg: Dict[str, Any]) -> None:
    safe_write_json(config_path(), cfg)


def load_presets() -> Dict[str, Any]:
    return safe_read_json(presets_path())


def save_presets(presets: Dict[str, Any]) -> None:
    safe_write_json(presets_path(), presets)


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def short_hash(text: str, n: int = 10) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()[:n]


# =========================================================
# File extraction
# =========================================================
def extract_text_from_pdf(file_obj) -> str:
    reader = PdfReader(file_obj)
    parts = []
    for page in reader.pages:
        txt = (page.extract_text() or "").strip()
        if txt:
            parts.append(txt)
    return "\n\n".join(parts).strip()


def extract_text_from_docx(file_obj) -> str:
    doc = Document(file_obj)
    return "\n".join([p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]).strip()


def extract_text_from_pptx(file_obj) -> str:
    prs = Presentation(file_obj)
    out = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text and shape.text.strip():
                out.append(shape.text.strip())
    return "\n".join(out).strip()


def extract_text(file_obj, filename: str) -> str:
    lower = (filename or "").lower()
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
    except Exception:
        pass

    if lower.endswith(".pdf"):
        return extract_text_from_pdf(file_obj)
    if lower.endswith(".docx"):
        return extract_text_from_docx(file_obj)
    if lower.endswith(".pptx"):
        return extract_text_from_pptx(file_obj)

    try:
        raw = file_obj.read()
        if isinstance(raw, str):
            return raw.strip()
        return raw.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def combine_uploaded_texts(files: List[Any], manual_text: str) -> str:
    parts = []
    for f in files or []:
        try:
            txt = extract_text(f, f.name)
            if txt.strip():
                parts.append(f"=== {f.name} ===\n{txt}")
        except Exception:
            continue
    if (manual_text or "").strip():
        parts.append(manual_text.strip())
    return "\n\n".join(parts).strip()


def extract_files_from_zip(zip_file) -> List[Dict[str, str]]:
    out = []
    try:
        if hasattr(zip_file, "seek"):
            zip_file.seek(0)
        raw = zip_file.read() if hasattr(zip_file, "read") else zip_file.getvalue()
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                fname = member.filename
                if not any(fname.lower().endswith(f".{ext}") for ext in UPLOAD_TYPES):
                    continue
                try:
                    with zf.open(member) as f:
                        data = f.read()
                    txt = extract_text(io.BytesIO(data), fname)
                    if txt.strip():
                        out.append({"name": fname, "text": txt})
                except Exception:
                    continue
    except Exception:
        return []
    return out


def normalize_uploaded_submissions(files: List[Any], zip_file: Optional[Any]) -> List[Dict[str, str]]:
    subs = []
    for f in files or []:
        try:
            txt = extract_text(f, f.name)
            if txt.strip():
                subs.append({"name": f.name, "text": txt})
        except Exception:
            continue

    if zip_file is not None:
        subs.extend(extract_files_from_zip(zip_file))

    dedup = []
    seen = set()
    for s in subs:
        key = (s["name"], short_hash(s["text"], 16))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(s)
    return dedup


# =========================================================
# LLM
# =========================================================
def get_client() -> Optional[OpenAI]:
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        cfg = load_config()
        key = (cfg.get("GROQ_API_KEY") or "").strip()
    if not key:
        return None
    return OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")


def llm_json(payload: Dict[str, Any], model: str = DEFAULT_MODEL, temperature: float = 0.15) -> Dict[str, Any]:
    client = get_client()
    if client is None:
        raise RuntimeError("GROQ_API_KEY is missing.")

    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are an academic grading assistant. Return valid JSON only, no markdown."
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False)
            }
        ],
        temperature=temperature,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except Exception:
        return {}


# =========================================================
# Models
# =========================================================
def sanitize_assignment_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    grounding = str(raw.get("grounding", "ai")).strip().lower()
    if grounding not in ["ai", "reference", "hybrid"]:
        grounding = "ai"

    pts = raw.get("points", 0)
    try:
        pts = int(pts)
    except Exception:
        pts = 0

    return {
        "item_origin": "assignment",
        "name": str(raw.get("name", "New Item")).strip() or "New Item",
        "description": str(raw.get("description", "")).strip(),
        "points": max(0, pts),
        "grounding": grounding,
        "expected_answer": "",
        "mode": "",
    }


def sanitize_teacher_key_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(raw.get("mode", "conceptual")).strip().lower()
    if mode not in ["exact", "conceptual"]:
        mode = "conceptual"

    grounding = str(raw.get("grounding", "ai")).strip().lower()
    if grounding not in ["ai", "reference", "hybrid"]:
        grounding = "ai"

    pts = raw.get("points", 0)
    try:
        pts = int(pts)
    except Exception:
        pts = 0

    if mode == "exact":
        grounding = ""

    return {
        "item_origin": "teacher_key",
        "name": str(raw.get("name", "New Item")).strip() or "New Item",
        "description": str(raw.get("description", "")).strip(),
        "points": max(0, pts),
        "grounding": grounding,
        "expected_answer": str(raw.get("expected_answer", "")).strip(),
        "mode": mode,
    }


def sanitize_item_by_origin(raw: Dict[str, Any], origin: str) -> Dict[str, Any]:
    return sanitize_teacher_key_item(raw) if origin == "teacher_key" else sanitize_assignment_item(raw)


def normalize_points(items: List[Dict[str, Any]], total_points: int, origin: str) -> List[Dict[str, Any]]:
    clean = [sanitize_item_by_origin(x, origin) for x in items if str(x.get("name", "")).strip()]
    if not clean:
        return []

    s = sum(int(x["points"]) for x in clean)
    if s <= 0:
        even = max(1, total_points // len(clean))
        clean = [{**x, "points": even} for x in clean]
        clean[0]["points"] += total_points - sum(y["points"] for y in clean)
        return clean

    out = []
    for x in clean:
        out.append({**x, "points": int(round(int(x["points"]) * total_points / s))})
    out[0]["points"] += total_points - sum(y["points"] for y in out)
    return out


def total_item_points(items: List[Dict[str, Any]]) -> int:
    return sum(int(x.get("points", 0)) for x in items)


def get_active_rubric_items_for_grade(
    grade_source: str,
    assignment_rubric_items: List[Dict[str, Any]],
    teacher_key_rubric_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if grade_source == "teacher_key":
        return list(teacher_key_rubric_items or [])
    return list(assignment_rubric_items or [])


# =========================================================
# Generation
# =========================================================
def generate_items_from_assignment(assignment_text: str, total_points: int) -> Dict[str, Any]:
    payload = {
        "task": "generate_rubric_from_assignment",
        "assignment_text": assignment_text,
        "target_total_points": total_points,
        "rules": [
            "Generate grading rubric items from the assignment text.",
            "Each item must include: name, description, points, grounding.",
            "Do not include exact or conceptual mode.",
            "grounding must be ai, reference, or hybrid.",
            "Use ai when general reasoning is enough.",
            "Use reference when course material or uploaded references should be the main basis.",
            "Use hybrid when both reasoning and reference grounding are useful.",
            "Points must be integers summing exactly to target_total_points."
        ],
        "output_json_schema": {
            "rubric_title": "string",
            "summary": ["string"],
            "items": [
                {
                    "name": "string",
                    "description": "string",
                    "points": "integer",
                    "grounding": "ai | reference | hybrid"
                }
            ]
        }
    }
    result = llm_json(payload, temperature=0.15)
    items = result.get("items", []) if isinstance(result, dict) else []
    result["items"] = normalize_points(items, total_points, "assignment")
    return result


def generate_items_from_teacher_key(teacher_key_text: str, total_points: int) -> Dict[str, Any]:
    payload = {
        "task": "generate_rubric_from_teacher_key",
        "teacher_key_text": teacher_key_text,
        "target_total_points": total_points,
        "rules": [
            "Generate grading items from the teacher key.",
            "Each item must include: name, description, expected_answer, points, mode.",
            "mode must be exact or conceptual.",
            "If the item is MCQ, true/false, matching, fixed-answer, one-word answer, or direct comparison style, use mode=exact.",
            "If the item is QA, explanation, open response, reasoning, or concept-based answer, use mode=conceptual.",
            "If mode is conceptual, include grounding with one of ai, reference, or hybrid.",
            "If mode is exact, grounding must be empty.",
            "Points must be integers summing exactly to target_total_points."
        ],
        "output_json_schema": {
            "rubric_title": "string",
            "summary": ["string"],
            "items": [
                {
                    "name": "string",
                    "description": "string",
                    "expected_answer": "string",
                    "points": "integer",
                    "mode": "exact | conceptual",
                    "grounding": "ai | reference | hybrid | empty-if-exact"
                }
            ]
        }
    }
    result = llm_json(payload, temperature=0.1)
    items = result.get("items", []) if isinstance(result, dict) else []
    result["items"] = normalize_points(items, total_points, "teacher_key")
    return result


# =========================================================
# RAG
# =========================================================
def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 120) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    out = []
    i = 0
    while i < len(text):
        out.append(text[i:i + chunk_size])
        i += max(1, chunk_size - overlap)
    return out


def rag_retrieve_for_item(item: Dict[str, Any], ref_text: str, top_k: int = 3) -> List[str]:
    chunks = chunk_text(ref_text)
    if not chunks:
        return []

    query = " ".join([
        str(item.get("name", "")),
        str(item.get("description", "")),
        str(item.get("expected_answer", "")),
    ]).lower()

    tokens = {t for t in re.split(r"\W+", query) if len(t) > 2}
    scored = []
    for chunk in chunks:
        low = chunk.lower()
        score = sum(1 for t in tokens if t in low)
        scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:top_k] if x[0] > 0]


def prepare_items_with_reference_context(items: List[Dict[str, Any]], reference_text: str) -> List[Dict[str, Any]]:
    prepared = []
    for item in items:
        item_copy = dict(item)

        if item_copy.get("item_origin") == "assignment":
            if item_copy.get("grounding") in ["reference", "hybrid"] and reference_text.strip():
                item_copy["reference_context"] = rag_retrieve_for_item(item_copy, reference_text, top_k=3)
            else:
                item_copy["reference_context"] = []

        elif item_copy.get("item_origin") == "teacher_key":
            if item_copy.get("mode") == "conceptual" and item_copy.get("grounding") in ["reference", "hybrid"] and reference_text.strip():
                item_copy["reference_context"] = rag_retrieve_for_item(item_copy, reference_text, top_k=3)
            else:
                item_copy["reference_context"] = []

        else:
            item_copy["reference_context"] = []

        prepared.append(item_copy)
    return prepared


# =========================================================
# Fast grading
# =========================================================
def grade_submission_fast(
    submission_text: str,
    items: List[Dict[str, Any]],
    teacher_key_text: str,
    reference_text: str,
) -> Dict[str, Any]:
    prepared_items = prepare_items_with_reference_context(items, reference_text)

    payload = {
        "task": "grade_entire_submission",
        "student_submission": submission_text,
        "teacher_key_text": teacher_key_text,
        "grading_items": prepared_items,
        "rules": [
            "Grade all items in a single pass.",
            "Assignment-origin items do not use exact/conceptual mode. Grade them using their grounding only.",
            "If an assignment-origin item grounding is ai, use reasoning.",
            "If an assignment-origin item grounding is reference, prioritize reference_context.",
            "If an assignment-origin item grounding is hybrid, use both reasoning and reference_context.",
            "Teacher-key-origin exact items should compare directly against expected_answer and teacher key.",
            "Teacher-key-origin conceptual items should grade by understanding, not exact wording.",
            "For teacher-key-origin conceptual items: use grounding ai/reference/hybrid.",
            "Return one result per item with earned_points, rationale, suggestions, evidence.",
            "earned_points must be between 0 and that item's points.",
            "Return overall_score and overall_out_of."
        ],
        "output_json_schema": {
            "overall_score": "number",
            "overall_out_of": "number",
            "items_results": [
                {
                    "name": "string",
                    "earned_points": "number",
                    "rationale": "string",
                    "suggestions": ["string"],
                    "evidence": [{"quote": "string", "source": "string"}]
                }
            ]
        }
    }

    res = llm_json(payload, temperature=0.1)
    raw_results = res.get("items_results", []) if isinstance(res, dict) else []

    by_name = {}
    for r in raw_results:
        name = str(r.get("name", "")).strip()
        if name:
            by_name[name] = r

    final_results = []
    total_earned = 0.0
    total_possible = 0

    for item in items:
        raw = by_name.get(item["name"], {})
        try:
            earned = float(raw.get("earned_points", 0))
        except Exception:
            earned = 0.0
        earned = max(0.0, min(float(item.get("points", 0)), earned))
        total_earned += earned
        total_possible += int(item.get("points", 0))

        final_results.append({
            "item_origin": item.get("item_origin", ""),
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "expected_answer": item.get("expected_answer", ""),
            "points": item.get("points", 0),
            "mode": item.get("mode", ""),
            "grounding": item.get("grounding", ""),
            "earned_points": round(earned, 2),
            "rationale": raw.get("rationale", ""),
            "suggestions": raw.get("suggestions", []),
            "evidence": raw.get("evidence", []),
        })

    return {
        "overall_score": round(total_earned, 2),
        "overall_out_of": total_possible,
        "items_results": final_results,
    }


def build_result_record(title: str, result: Dict[str, Any], submission_text: str) -> Dict[str, Any]:
    return {
        "id": f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{short_hash(submission_text, 8)}",
        "timestamp": now_iso(),
        "title": title,
        "overall_score": result.get("overall_score", 0),
        "overall_out_of": result.get("overall_out_of", 0),
        "items_results": result.get("items_results", []),
        "submission_preview": (submission_text or "")[:1200],
    }


# =========================================================
# Exports
# =========================================================
def export_single_report(record: Dict[str, Any]) -> str:
    lines = []
    lines.append("ORGANIZED GRADING REPORT")
    lines.append("=" * 90)
    lines.append(f"Title: {record.get('title', '(untitled)')}")
    lines.append(f"Generated: {record.get('timestamp', '')}")
    lines.append(f"Record ID: {record.get('id', '')}")
    lines.append(f"Overall Score: {record.get('overall_score', 0)} / {record.get('overall_out_of', 0)}")
    lines.append("")
    lines.append("ITEM-BY-ITEM RESULTS")
    lines.append("-" * 90)

    for idx, item in enumerate(record.get("items_results", []), start=1):
        lines.append(f"{idx}. {item.get('name', 'Item')}")
        lines.append(f"   Origin: {item.get('item_origin', '')}")
        if item.get("description"):
            lines.append(f"   Description: {item.get('description')}")
        if item.get("mode"):
            lines.append(f"   Mode: {item.get('mode', '')}")
        if item.get("grounding"):
            lines.append(f"   Grounding: {item.get('grounding', '')}")
        lines.append(f"   Points: {item.get('earned_points', 0)} / {item.get('points', 0)}")
        if item.get("expected_answer"):
            lines.append(f"   Expected Answer / Guide: {item.get('expected_answer')}")
        if item.get("rationale"):
            lines.append(f"   Rationale: {item.get('rationale')}")
        for s in item.get("suggestions", []) or []:
            lines.append(f"   Suggestion: {s}")
        for e in item.get("evidence", [])[:3]:
            quote = (e.get("quote") or "").strip()
            source = (e.get("source") or "").strip()
            if quote:
                lines.append(f"   Evidence: {quote}" + (f" [{source}]" if source else ""))
        lines.append("")
    return "\n".join(lines)


def export_batch_report(records: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("BATCH GRADING REPORT")
    lines.append("=" * 90)
    lines.append(f"Generated: {now_iso()}")
    lines.append(f"Number of submissions: {len(records)}")
    lines.append("")
    lines.append("RANKING")
    lines.append("-" * 90)
    for i, r in enumerate(records, start=1):
        lines.append(f"{i}. {r.get('title', '(untitled)')} -> {r.get('overall_score', 0)} / {r.get('overall_out_of', 0)}")
    lines.append("")
    lines.append("DETAILED REPORTS")
    lines.append("-" * 90)
    lines.append("")
    for r in records:
        lines.append(export_single_report(r))
        lines.append("")
        lines.append("=" * 90)
        lines.append("")
    return "\n".join(lines)


def build_docx_report(record: Dict[str, Any]) -> bytes:
    doc = Document()

    title = doc.add_heading("Grading Report", level=0)
    title.alignment = 1

    p = doc.add_paragraph()
    p.add_run("Title: ").bold = True
    p.add_run(str(record.get("title", "(untitled)")))

    p = doc.add_paragraph()
    p.add_run("Generated: ").bold = True
    p.add_run(str(record.get("timestamp", "")))

    p = doc.add_paragraph()
    p.add_run("Record ID: ").bold = True
    p.add_run(str(record.get("id", "")))

    p = doc.add_paragraph()
    p.add_run("Overall Score: ").bold = True
    p.add_run(f"{record.get('overall_score', 0)} / {record.get('overall_out_of', 0)}")

    doc.add_paragraph("")
    doc.add_heading("Item-by-Item Results", level=1)

    for idx, item in enumerate(record.get("items_results", []), start=1):
        doc.add_heading(f"{idx}. {item.get('name', 'Item')}", level=2)

        p = doc.add_paragraph()
        p.add_run("Origin: ").bold = True
        p.add_run(str(item.get("item_origin", "")))

        if item.get("description"):
            p = doc.add_paragraph()
            p.add_run("Description: ").bold = True
            p.add_run(str(item.get("description", "")))

        if item.get("mode"):
            p = doc.add_paragraph()
            p.add_run("Mode: ").bold = True
            p.add_run(str(item.get("mode", "")))

        if item.get("grounding"):
            p = doc.add_paragraph()
            p.add_run("Grounding: ").bold = True
            p.add_run(str(item.get("grounding", "")))

        p = doc.add_paragraph()
        p.add_run("Points: ").bold = True
        p.add_run(f"{item.get('earned_points', 0)} / {item.get('points', 0)}")

        if item.get("expected_answer"):
            p = doc.add_paragraph()
            p.add_run("Expected Answer / Guide: ").bold = True
            p.add_run(str(item.get("expected_answer", "")))

        if item.get("rationale"):
            p = doc.add_paragraph()
            p.add_run("Rationale: ").bold = True
            p.add_run(str(item.get("rationale", "")))

        if item.get("suggestions"):
            doc.add_paragraph("Suggestions:")
            for s in item.get("suggestions", []):
                doc.add_paragraph(str(s), style="List Bullet")

        if item.get("evidence"):
            doc.add_paragraph("Evidence:")
            for e in item.get("evidence", [])[:3]:
                quote = (e.get("quote") or "").strip()
                source = (e.get("source") or "").strip()
                if quote:
                    line = quote + (f" [{source}]" if source else "")
                    doc.add_paragraph(line, style="List Bullet")

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()


def build_batch_docx_report(records: List[Dict[str, Any]]) -> bytes:
    doc = Document()

    title = doc.add_heading("Batch Grading Report", level=0)
    title.alignment = 1

    p = doc.add_paragraph()
    p.add_run("Generated: ").bold = True
    p.add_run(now_iso())

    p = doc.add_paragraph()
    p.add_run("Number of submissions: ").bold = True
    p.add_run(str(len(records)))

    doc.add_heading("Ranking", level=1)
    for i, r in enumerate(records, start=1):
        doc.add_paragraph(
            f"{i}. {r.get('title', '(untitled)')} -> {r.get('overall_score', 0)} / {r.get('overall_out_of', 0)}",
            style="List Number"
        )

    doc.add_page_break()
    doc.add_heading("Detailed Reports", level=1)

    for idx, record in enumerate(records, start=1):
        doc.add_heading(f"{idx}. {record.get('title', '(untitled)')}", level=2)

        p = doc.add_paragraph()
        p.add_run("Generated: ").bold = True
        p.add_run(str(record.get("timestamp", "")))

        p = doc.add_paragraph()
        p.add_run("Overall Score: ").bold = True
        p.add_run(f"{record.get('overall_score', 0)} / {record.get('overall_out_of', 0)}")

        for j, item in enumerate(record.get("items_results", []), start=1):
            doc.add_heading(f"{j}. {item.get('name', 'Item')}", level=3)

            if item.get("description"):
                p = doc.add_paragraph()
                p.add_run("Description: ").bold = True
                p.add_run(str(item.get("description", "")))

            if item.get("mode"):
                p = doc.add_paragraph()
                p.add_run("Mode: ").bold = True
                p.add_run(str(item.get("mode", "")))

            if item.get("grounding"):
                p = doc.add_paragraph()
                p.add_run("Grounding: ").bold = True
                p.add_run(str(item.get("grounding", "")))

            p = doc.add_paragraph()
            p.add_run("Points: ").bold = True
            p.add_run(f"{item.get('earned_points', 0)} / {item.get('points', 0)}")

            if item.get("rationale"):
                p = doc.add_paragraph()
                p.add_run("Rationale: ").bold = True
                p.add_run(str(item.get("rationale", "")))

        if idx < len(records):
            doc.add_page_break()

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()


def build_single_report_html(record: Dict[str, Any]) -> str:
    rows = []
    for idx, item in enumerate(record.get("items_results", []), start=1):
        suggestions = "".join(f"<li>{s}</li>" for s in item.get("suggestions", []))
        evidence = "".join(
            f"<li>{(e.get('quote') or '').strip()}</li>"
            for e in item.get("evidence", [])[:3]
            if (e.get("quote") or "").strip()
        )

        rows.append(f"""
        <div class="item">
            <h3>{idx}. {item.get("name", "Item")}</h3>
            <div class="meta">
                <span>Origin: {item.get("item_origin", "")}</span>
                <span>Mode: {item.get("mode", "")}</span>
                <span>Grounding: {item.get("grounding", "")}</span>
                <span>Points: {item.get("earned_points", 0)} / {item.get("points", 0)}</span>
            </div>
            <p><strong>Description:</strong> {item.get("description", "")}</p>
            <p><strong>Expected Answer / Guide:</strong> {item.get("expected_answer", "")}</p>
            <p><strong>Rationale:</strong> {item.get("rationale", "")}</p>
            {"<div><strong>Suggestions:</strong><ul>" + suggestions + "</ul></div>" if suggestions else ""}
            {"<div><strong>Evidence:</strong><ul>" + evidence + "</ul></div>" if evidence else ""}
        </div>
        """)

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>Grading Report</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 40px;
                color: #1c2430;
                background: #ffffff;
            }}
            .header {{
                border-bottom: 2px solid #d9e2ef;
                padding-bottom: 16px;
                margin-bottom: 24px;
            }}
            h1 {{
                margin: 0 0 10px 0;
                color: #1c2430;
            }}
            .score-box {{
                background: #f4f8fc;
                border: 1px solid #d9e2ef;
                border-radius: 12px;
                padding: 14px 16px;
                display: inline-block;
                margin-top: 8px;
                font-weight: bold;
            }}
            .item {{
                border: 1px solid #e2eaf3;
                border-radius: 14px;
                padding: 16px;
                margin-bottom: 18px;
                background: #fafcff;
            }}
            .meta {{
                display: flex;
                gap: 14px;
                flex-wrap: wrap;
                font-size: 13px;
                color: #5b6c83;
                margin-bottom: 10px;
            }}
            h3 {{
                margin-top: 0;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Grading Report</h1>
            <p><strong>Title:</strong> {record.get("title", "(untitled)")}</p>
            <p><strong>Generated:</strong> {record.get("timestamp", "")}</p>
            <p><strong>Record ID:</strong> {record.get("id", "")}</p>
            <div class="score-box">Overall Score: {record.get("overall_score", 0)} / {record.get("overall_out_of", 0)}</div>
        </div>
        {''.join(rows)}
    </body>
    </html>
    """


def build_batch_report_html(records: List[Dict[str, Any]]) -> str:
    ranking = "".join(
        f"<li>{r.get('title', '(untitled)')} — {r.get('overall_score', 0)} / {r.get('overall_out_of', 0)}</li>"
        for r in records
    )

    blocks = []
    for r in records:
        blocks.append(f"""
        <div class="submission">
            <h2>{r.get("title", "(untitled)")}</h2>
            <p><strong>Generated:</strong> {r.get("timestamp", "")}</p>
            <div class="score-box">Score: {r.get("overall_score", 0)} / {r.get("overall_out_of", 0)}</div>
        </div>
        """)

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>Batch Grading Report</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 40px;
                color: #1c2430;
                background: #ffffff;
            }}
            h1, h2 {{
                color: #1c2430;
            }}
            .section {{
                margin-bottom: 28px;
            }}
            .submission {{
                border: 1px solid #e2eaf3;
                border-radius: 14px;
                padding: 16px;
                margin-bottom: 16px;
                background: #fafcff;
            }}
            .score-box {{
                background: #f4f8fc;
                border: 1px solid #d9e2ef;
                border-radius: 12px;
                padding: 10px 14px;
                display: inline-block;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div class="section">
            <h1>Batch Grading Report</h1>
            <p><strong>Generated:</strong> {now_iso()}</p>
            <p><strong>Number of submissions:</strong> {len(records)}</p>
        </div>

        <div class="section">
            <h2>Ranking</h2>
            <ol>{ranking}</ol>
        </div>

        <div class="section">
            <h2>Submissions</h2>
            {''.join(blocks)}
        </div>
    </body>
    </html>
    """


