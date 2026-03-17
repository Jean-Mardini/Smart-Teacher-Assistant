"""Quiz generator agent implementation (owned by Angela)."""

from pathlib import Path
from typing import List, Dict, Any

from app.services.llm.groq_client import call_llm_json
from app.models.agents import QuizResult


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "quiz.md"


# ----------------------------------------
# BUILD DOCUMENT TEXT
# ----------------------------------------
def build_full_text(document_json: dict) -> str:
    parts = []

    for s in document_json.get("sections", []):
        parts.append(f"{s.get('heading','')}\n{s.get('text','')}")

    for t in document_json.get("tables", []):
        parts.append(f"Table: {t.get('caption','')}\n{t.get('text','')}")

    for img in document_json.get("images", []):
        parts.append(f"Image: {img.get('caption','')}\n{img.get('description','')}")

    return "\n\n".join(parts)


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
def normalize_question(q: Dict[str, Any]) -> Dict[str, Any]:
    q_type = q.get("type", "mcq")

    item = {
        "type": q_type,
        "question": q.get("question", "").strip(),
        "explanation": q.get("explanation", "").strip(),
        "difficulty": q.get("difficulty", "medium"),
        "source_refs": q.get("source_refs", []),
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

    # ---------- SHORT ANSWER ----------
    else:
        item["options"] = []
        item["answer_text"] = q.get("answer_text", "").strip()

    return item


# ----------------------------------------
# MAIN QUIZ FUNCTION
# ----------------------------------------
async def run_quiz(
    doc_json: dict,
    n_questions: int,
    difficulty: str = "medium"
) -> QuizResult:

    try:
        # -------- LOAD PROMPT --------
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        prompt = prompt.replace("{N_QUESTIONS}", str(n_questions))

        # -------- BUILD TEXT --------
        full_text = build_full_text(doc_json)

        if not full_text.strip():
            return QuizResult(quiz=[])

        # -------- LLM CALL --------
        system = "Return ONLY valid JSON. No explanations."

        user = f"""
{prompt}

DIFFICULTY: {difficulty}

TEXT:
{full_text}
"""

        raw = call_llm_json(system, user)

        print("🧠 QUIZ RAW:", raw)

        if not raw:
            return QuizResult(quiz=[])

        # -------- EXTRACT QUESTIONS --------
        questions = raw.get("quiz") or raw.get("questions") or []

        fixed_quiz = []

        for q in questions:
            try:
                fixed_quiz.append(normalize_question(q))
            except Exception as inner_error:
                print("⚠️ Skipping bad question:", inner_error)

        # -------- LIMIT TO REQUESTED NUMBER --------
        if len(fixed_quiz) > n_questions:
            fixed_quiz = fixed_quiz[:n_questions]

        return QuizResult(quiz=fixed_quiz)

    except Exception as e:
        print("❌ QUIZ AGENT ERROR:", e)
        return QuizResult(quiz=[])