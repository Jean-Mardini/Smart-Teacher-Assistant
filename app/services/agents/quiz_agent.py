"""Quiz generator agent implementation (owned by Angela)."""

import logging
from pathlib import Path
from typing import Any, Dict, List

from app.models.agents import QuizResult
from app.services.llm.groq_client import call_llm_json, call_llm_json_object, truncate_text_for_quiz_prompt

logger = logging.getLogger(__name__)


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "quiz.md"


# ----------------------------------------
# BUILD DOCUMENT TEXT
# ----------------------------------------
def build_full_text(document_json: dict) -> str:
    """Prefer structured sections/tables/images; fall back to ``full_text`` (indexed PDFs always set it)."""
    parts: list[str] = []

    for s in document_json.get("sections", []) or []:
        if isinstance(s, dict):
            parts.append(f"{s.get('heading', '')}\n{s.get('text', '')}")

    for t in document_json.get("tables", []) or []:
        if isinstance(t, dict):
            parts.append(f"Table: {t.get('caption', '')}\n{t.get('text', '')}")

    for img in document_json.get("images", []) or []:
        if isinstance(img, dict):
            parts.append(f"Image: {img.get('caption', '')}\n{img.get('description', '')}")

    joined = "\n\n".join(p for p in parts if str(p).strip())
    if joined.strip():
        return joined

    fallback = (document_json.get("full_text") or "").strip()
    if fallback:
        return fallback

    title = (document_json.get("title") or "").strip()
    if title:
        return title

    return ""


# ----------------------------------------
# FORCE MCQ FORMAT (A/B/C/D)
# ----------------------------------------
def enforce_mcq_format(options: List[str]) -> List[str]:
    labels = ["A", "B", "C", "D"]
    fixed = []

    for i, opt in enumerate(options[:4]):
        text = opt.strip()

        # remove any existing labels
        for l in labels:
            text = text.replace(f"{l}.", "").strip()

        fixed.append(f"{labels[i]}. {text}")

    # ensure exactly 4 options
    while len(fixed) < 4:
        fixed.append(f"{labels[len(fixed)]}. Option")

    return fixed


# ----------------------------------------
# SAFE QUESTION CLEANER
# ----------------------------------------
def _canonical_difficulty(raw: Any) -> str:
    s = str(raw or "medium").strip().lower()
    if s in ("easy", "medium", "hard"):
        return s
    return "medium"


def _coerce_source_refs(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def _canonical_qtype(raw: Any, q: Dict[str, Any]) -> str:
    """Map model aliases to ``mcq`` | ``short_answer`` | ``true_false`` so filtering keeps questions."""
    s = str(raw or "").strip().lower().replace("-", "_").replace(" ", "")
    if s in (
        "true_false",
        "truefalse",
        "trueorfalse",
        "boolean",
        "bool",
        "t_f",
        "tf",
    ):
        return "true_false"
    if s in (
        "short_answer",
        "shortanswer",
        "short",
        "sa",
        "freeresponse",
        "freetext",
        "openended",
        "open",
        "essay",
    ):
        return "short_answer"
    if s in ("mcq", "multiple_choice", "multichoice", "choice", "multiplechoice"):
        return "mcq"
    if "short" in s or "free" in s or "open" in s:
        return "short_answer"
    if "mcq" in s or "choice" in s:
        return "mcq"
    opts = q.get("options")
    if isinstance(opts, list) and len([x for x in opts if str(x).strip()]) >= 2:
        return "mcq"
    return "short_answer"


def normalize_question(q: Dict[str, Any]) -> Dict[str, Any]:
    q_type = _canonical_qtype(q.get("type"), q)

    item = {
        "type": q_type,
        "question": q.get("question", "").strip(),
        "explanation": (q.get("explanation") or "").strip() or "See document context.",
        "difficulty": _canonical_difficulty(q.get("difficulty")),
        "source_refs": _coerce_source_refs(q.get("source_refs")),
    }

    # ---------- MCQ ----------
    if q_type == "mcq":
        options = enforce_mcq_format(q.get("options", []))

        answer_index = q.get("answer_index")
        if answer_index not in [0, 1, 2, 3]:
            answer_index = 0

        correct_option = options[answer_index]

        item["options"] = options
        item["answer_index"] = answer_index
        item["answer_text"] = correct_option  # ✅ "A. Angela"

    # ---------- TRUE / FALSE ----------
    elif q_type == "true_false":
        options = ["A. True", "B. False"]
        answer_index = q.get("answer_index")
        if answer_index not in (0, 1):
            answer_index = None
        if answer_index is None:
            at = str(q.get("answer_text") or "").strip().lower()
            if at in ("false", "f", "no", "0", "b", "b.", "b. false", "b false"):
                answer_index = 1
            elif at in ("true", "t", "yes", "1", "a", "a.", "a. true", "a true"):
                answer_index = 0
            else:
                answer_index = 0
        item["options"] = options
        item["answer_index"] = int(answer_index)
        item["answer_text"] = options[item["answer_index"]]

    # ---------- SHORT ANSWER ----------
    else:
        item["options"] = []
        item["answer_text"] = q.get("answer_text", "").strip()

    return item


def _distribute_points(questions: List[Dict[str, Any]], total: int) -> List[Dict[str, Any]]:
    """Assign integer ``points`` per question so the sum equals ``total`` (at least one per question)."""
    n = len(questions)
    if n == 0:
        return questions
    total_i = max(n, min(2000, int(total)))
    base = total_i // n
    rem = total_i % n
    for i, q in enumerate(questions):
        q["points"] = base + (1 if i < rem else 0)
    return questions


# ----------------------------------------
# MAIN QUIZ FUNCTION
# ----------------------------------------
async def run_quiz(
    doc_json: dict,
    n_mcq: int,
    n_short_answer: int,
    difficulty: str = "medium",
    total_points: int = 10,
    n_true_false: int = 0,
) -> QuizResult:
    n_mcq = max(0, min(100, int(n_mcq)))
    n_short_answer = max(0, min(100, int(n_short_answer)))
    n_true_false = max(0, min(100, int(n_true_false)))
    n_total = n_mcq + n_short_answer + n_true_false
    quiz_title_out = ((doc_json.get("title") or "").strip()) or None

    if n_total < 1:
        return QuizResult(quiz=[], quiz_title=quiz_title_out)

    try:
        # -------- LOAD PROMPT --------
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        tp = max(n_total, min(2000, int(total_points)))
        prompt = (
            prompt.replace("{N_MCQ}", str(n_mcq))
            .replace("{N_SHORT}", str(n_short_answer))
            .replace("{N_TF}", str(n_true_false))
            .replace("{N_TOTAL}", str(n_total))
            .replace("{TOTAL_POINTS}", str(tp))
        )

        # -------- BUILD TEXT --------
        full_text = build_full_text(doc_json)

        if not full_text.strip():
            logger.warning("Quiz skipped: no document text (sections empty and full_text missing)")
            return QuizResult(quiz=[], quiz_title=quiz_title_out)

        source_for_llm, truncated = truncate_text_for_quiz_prompt(full_text)
        if truncated:
            logger.info("Quiz document truncated for Groq context limit")

        # -------- LLM CALL (json_object = valid root dict from Groq) --------
        system = (
            "You are an expert assessment author. Output a single JSON object only (no markdown). "
            'The object must have exactly one top-level key \"quiz\" whose value is an array of questions. '
            "Each question object follows the user's schema."
        )

        user = f"""
{prompt}

DIFFICULTY: {difficulty}
QUIZ TOTAL (marks): {tp} points across all {n_total} questions.

TEXT:
{source_for_llm}
"""

        try:
            raw = call_llm_json_object(system, user, temperature=0.25)
        except Exception as exc:
            logger.warning("Quiz json_object mode failed (%s); falling back to legacy JSON parse", exc)
            raw = call_llm_json(
                system + " If json_object mode is unavailable, still return one JSON object only.",
                user,
                temperature=0.2,
            )

        logger.debug("Quiz raw keys: %s", list(raw.keys()) if isinstance(raw, dict) else type(raw))

        if not raw:
            return QuizResult(quiz=[], quiz_title=quiz_title_out)

        # -------- EXTRACT QUESTIONS --------
        questions: list[Any] = []
        if isinstance(raw, list):
            questions = raw
        elif isinstance(raw, dict):
            questions = (
                raw.get("quiz")
                or raw.get("questions")
                or raw.get("items")
                or raw.get("data")
                or []
            )
            if isinstance(questions, dict):
                questions = list(questions.values())

        if not isinstance(questions, list):
            questions = []

        fixed_quiz: list[Dict[str, Any]] = []

        for q in questions:
            if not isinstance(q, dict):
                continue
            try:
                fixed_quiz.append(normalize_question(q))
            except Exception as inner_error:
                logger.warning("Skipping bad quiz question: %s", inner_error)

        # -------- LIMIT TO REQUESTED COUNTS PER TYPE --------
        fixed_quiz = [q for q in fixed_quiz if (q.get("question") or "").strip()]
        mcqs = [q for q in fixed_quiz if q.get("type") == "mcq"]
        tfs = [q for q in fixed_quiz if q.get("type") == "true_false"]
        shorts = [q for q in fixed_quiz if q.get("type") == "short_answer"]
        fixed_quiz = _distribute_points(
            mcqs[:n_mcq] + tfs[:n_true_false] + shorts[:n_short_answer],
            tp,
        )

        return QuizResult(quiz=fixed_quiz, quiz_title=quiz_title_out)

    except Exception as e:
        logger.exception("Quiz agent error: %s", e)
        return QuizResult(quiz=[], quiz_title=quiz_title_out)