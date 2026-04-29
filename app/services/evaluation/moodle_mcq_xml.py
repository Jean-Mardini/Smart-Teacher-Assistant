"""Deterministic grading for Moodle quiz XML (MCQ / true-false / short answer).

Both the answer key and the learner file must be Moodle ``<quiz>`` exports using
``<question>`` elements (as produced by Moodle or by this app's quiz export).
The learner file must use the **same** ``<name><text>`` identifiers as the key.

**Selections:** For each question, learner choices are the ``<answer>`` rows whose
``fraction`` equals the **maximum** ``fraction`` among answers in that question
in the learner XML (multi-select: multiple rows may share that maximum).

**Partial credit (multi-correct):** If the key lists *n* correct options (same max
positive ``fraction``), the question score is split into *n* equal parts. The
learner's net correct selections are ``(# correct chosen − # incorrect chosen)``,
clamped to ``[0, n]``, then ``earned = (net / n) × question_points``. One wrong
selection cancels one correct unit of credit.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _local_text(parent: ET.Element | None, path: tuple[str, ...]) -> str:
    if parent is None:
        return ""
    cur: ET.Element | None = parent
    for part in path:
        cur = cur.find(part) if cur is not None else None
        if cur is None:
            return ""
    if cur is not None and cur.text:
        return str(cur.text).strip()
    return ""


def _collect_answers(question: ET.Element) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for child in question:
        if _strip_ns(child.tag) != "answer":
            continue
        frac_raw = child.get("fraction", "0") or "0"
        try:
            frac = float(frac_raw)
        except ValueError:
            frac = 0.0
        text = _local_text(child, ("text",))
        if not text:
            # nested format
            for tnode in child.iter():
                if _strip_ns(tnode.tag) == "text" and tnode.text:
                    text = str(tnode.text).strip()
                    break
        out.append({"fraction": frac, "text": text or ""})
    return out


def _normalize_answer_text(raw: str) -> str:
    s = unescape(raw or "")
    s = re.sub(r"<[^>]+>", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _max_fraction_texts(answers: list[dict[str, Any]]) -> list[str]:
    if not answers:
        return []
    mx = max((a["fraction"] for a in answers), default=0.0)
    if mx <= 0:
        return []
    texts = [_normalize_answer_text(a["text"]) for a in answers if abs(a["fraction"] - mx) < 1e-6 and a.get("text")]
    # de-dupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for t in texts:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def parse_moodle_question_bank(xml: str) -> dict[str, dict[str, Any]]:
    """Parse ``<quiz>`` XML into a map keyed by question ``<name><text>``."""
    root = ET.fromstring(xml.strip())
    if _strip_ns(root.tag) != "quiz":
        raise ValueError("Root element must be <quiz> (Moodle XML).")

    out: dict[str, dict[str, Any]] = {}
    for question in root:
        if _strip_ns(question.tag) != "question":
            continue
        q_type = (question.get("type") or "").strip().lower()
        if q_type == "category":
            continue

        name = _local_text(question, ("name", "text"))
        if not name:
            inner = question.find("name")
            if inner is not None:
                for tnode in inner.iter():
                    if _strip_ns(tnode.tag) == "text" and tnode.text:
                        name = str(tnode.text).strip()
                        break
        if not name:
            continue

        key = name.strip()
        if key in out:
            suffix = 2
            while f"{key} ({suffix})" in out:
                suffix += 1
            key = f"{key} ({suffix})"

        dg_raw = ""
        dg_el = question.find("defaultgrade")
        if dg_el is not None and dg_el.text:
            dg_raw = str(dg_el.text).strip()
        try:
            default_grade = float(dg_raw or "1")
        except ValueError:
            default_grade = 1.0

        answers = _collect_answers(question)
        correct = _max_fraction_texts(answers)
        stem = _local_text(question, ("questiontext", "text"))
        if not stem:
            qt = question.find("questiontext")
            if qt is not None:
                for tnode in qt.iter():
                    if _strip_ns(tnode.tag) == "text" and tnode.text:
                        stem = str(tnode.text).strip()
                        break

        out[key] = {
            "name": name.strip(),
            "qtype": q_type or "unknown",
            "defaultgrade": max(0.0, default_grade),
            "correct_texts": correct,
            "answers": answers,
            "stem": stem,
        }
    if not out:
        raise ValueError("No gradable questions found in Moodle XML (expected <question> elements).")
    return out


def _answer_sets_for_question(
    correct_texts: list[str],
    chosen_texts: list[str],
    question_points: float,
) -> tuple[float, str]:
    """Partial credit when multiple keyed correct answers exist.

    Each of *n* keyed correct options is worth ``question_points / n``.
    Net units = ``|chosen ∩ correct| − |chosen − correct|``, clamped to ``[0, n]``.
    Earned = ``(net / n) * question_points``.
    """
    r_set = {t for t in correct_texts if t}
    c_set = {t for t in chosen_texts if t}
    n = len(r_set)
    pts = float(max(0.0, question_points))
    if n <= 0:
        return 0.0, "No keyed correct answers in XML; scored 0 for this question."

    correct_selected = len(c_set & r_set)
    wrong_selected = len(c_set - r_set)
    net = correct_selected - wrong_selected
    net_clamped = max(0, min(n, net))
    earned = (net_clamped / n) * pts
    unit = pts / n if n else 0.0
    rationale = (
        f"Key has {n} correct option(s) (~{unit:.2f} pt each). "
        f"Learner matched {correct_selected}, chose {wrong_selected} incorrect. "
        f"Net = {correct_selected} − {wrong_selected} = {net} → use {net_clamped}/{n} of full credit."
    )
    return round(earned, 2), rationale


def grade_moodle_xml_pair(key_xml: str, student_xml: str) -> dict[str, Any]:
    """Return the same shape as ``grade_submission_fast`` for history / UI."""
    key = parse_moodle_question_bank(key_xml)
    stu = parse_moodle_question_bank(student_xml)

    items_results: list[dict[str, Any]] = []
    total_earned = 0.0
    total_out = 0

    for qname, k in key.items():
        pts = int(round(max(0.0, k["defaultgrade"])))
        total_out += pts
        st = stu.get(qname)
        if not st:
            items_results.append(
                {
                    "item_origin": "teacher_key",
                    "name": qname,
                    "description": (k.get("stem") or "")[:800],
                    "expected_answer": ", ".join(k.get("correct_texts") or []),
                    "points": pts,
                    "mode": "exact",
                    "grounding": "",
                    "earned_points": 0.0,
                    "rationale": "No matching question in the learner Moodle XML (check <name><text> matches the key).",
                    "suggestions": [],
                    "evidence": [],
                    "matched_key_ideas": [],
                    "missing_key_ideas": [],
                    "misconceptions": [],
                }
            )
            continue

        chosen = _max_fraction_texts(st.get("answers") or [])
        correct = k.get("correct_texts") or []
        earned, rat = _answer_sets_for_question(correct, chosen, float(pts))
        total_earned += earned
        r_set = {t for t in correct if t}
        c_set = {t for t in chosen if t}
        full_credit = float(pts) > 0 and abs(earned - float(pts)) < 1e-6
        matched = sorted(r_set & c_set)
        missing = sorted(r_set - c_set)
        wrong_picks = sorted(c_set - r_set)

        items_results.append(
            {
                "item_origin": "teacher_key",
                "name": qname,
                "description": (k.get("stem") or "")[:800],
                "expected_answer": ", ".join(correct),
                "points": pts,
                "mode": "exact",
                "grounding": "",
                "earned_points": earned,
                "rationale": rat,
                "suggestions": []
                if full_credit and not wrong_picks
                else [
                    "Compare learner XML to the key: same <name><text> per question; "
                    "chosen answers are <answer> rows sharing the highest fraction in that question."
                ],
                "evidence": [],
                "matched_key_ideas": matched,
                "missing_key_ideas": missing,
                "misconceptions": wrong_picks,
            }
        )

    return {
        "overall_score": round(total_earned, 2),
        "overall_out_of": total_out,
        "items_results": items_results,
    }


def rubric_items_from_key_xml(key_xml: str) -> list[dict[str, Any]]:
    """Build rubric ``items`` for display / presets (exact MCQ rows)."""
    key = parse_moodle_question_bank(key_xml)
    items: list[dict[str, Any]] = []
    for qname, k in key.items():
        pts = int(round(max(0.0, k["defaultgrade"])))
        items.append(
            {
                "item_origin": "teacher_key",
                "name": qname,
                "description": (k.get("stem") or "")[:800],
                "expected_answer": ", ".join(k.get("correct_texts") or []),
                "points": max(1, pts),
                "mode": "exact",
                "grounding": "",
            }
        )
    return items
