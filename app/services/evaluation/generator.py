"""Assignment, exam, and lesson-plan generation powered by the shared Groq client."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.services.llm import groq_client

logger = logging.getLogger(__name__)


def generate_assignment(
    source_text: str,
    difficulty: str = "medium",
    total_points: int = 100,
    task_count: int = 5,
) -> Dict[str, Any]:
    payload = {
        "task": "generate_assignment",
        "source_material": source_text[:9000],
        "difficulty": difficulty,
        "total_points": total_points,
        "task_count": task_count,
        "rules": [
            "Generate a complete assignment from the source material.",
            f"Difficulty: {difficulty}. Adjust language complexity and depth accordingly.",
            f"Include exactly {task_count} clearly numbered tasks.",
            f"Point values across tasks must sum to exactly {total_points}.",
            "Include a clear objective and submission instructions.",
            "Generate rubric_items that can grade this assignment.",
            "rubric_items: grounding must be one of ai, reference, hybrid.",
            "rubric_items: do NOT include mode or expected_answer fields.",
            "rubric_items point values must also sum to exactly total_points.",
        ],
        "output_json_schema": {
            "title": "string",
            "objective": "string",
            "instructions": "string",
            "tasks": [{"number": 1, "description": "string", "points": 10}],
            "submission_requirements": "string",
            "rubric_items": [
                {"name": "string", "description": "string", "points": 10, "grounding": "ai|reference|hybrid"}
            ],
        },
    }
    return groq_client.call_llm_json_payload(payload, temperature=0.3)


def generate_exam(
    source_text: str,
    difficulty: str = "medium",
    total_points: int = 100,
    question_types: List[str] | None = None,
    question_count: int = 10,
) -> Dict[str, Any]:
    types = question_types or ["short_answer"]
    types_str = ", ".join(types)
    payload = {
        "task": "generate_exam",
        "source_material": source_text[:9000],
        "difficulty": difficulty,
        "total_points": total_points,
        "question_count": question_count,
        "allowed_question_types": types,
        "rules": [
            "Generate a complete exam paper from the source material.",
            f"Difficulty: {difficulty}.",
            f"Include exactly {question_count} questions using only these types: {types_str}.",
            f"Point values across questions must sum to exactly {total_points}.",
            "MCQ: include exactly 4 options as ['A. …', 'B. …', 'C. …', 'D. …'] and an answer field (e.g. 'A').",
            "true_false: include options ['True', 'False'] and an answer field.",
            "short_answer and essay: include an expected_answer summarising the ideal response.",
            "Generate rubric_items for grading this exam.",
            "MCQ and true_false rubric items: mode=exact, grounding='' (empty).",
            "short_answer and essay rubric items: mode=conceptual, grounding=ai|reference|hybrid.",
            "rubric_items point values must also sum to exactly total_points.",
        ],
        "output_json_schema": {
            "title": "string",
            "instructions": "string",
            "duration": "string",
            "questions": [
                {
                    "number": 1,
                    "type": "mcq|short_answer|essay|true_false",
                    "question": "string",
                    "options": ["A. …"],
                    "answer": "string",
                    "points": 10,
                }
            ],
            "rubric_items": [
                {
                    "name": "string",
                    "description": "string",
                    "points": 10,
                    "mode": "exact|conceptual",
                    "grounding": "ai|reference|hybrid|empty",
                    "expected_answer": "string",
                }
            ],
        },
    }
    return groq_client.call_llm_json_payload(payload, temperature=0.15)


def generate_lesson_plan(
    weak_criteria: List[Dict[str, Any]],
    class_average_pct: float,
    context: str = "",
) -> Dict[str, Any]:
    payload = {
        "task": "generate_lesson_plan",
        "class_average_percent": round(class_average_pct, 1),
        "weak_criteria": weak_criteria,
        "subject_context": context or "general subject",
        "rules": [
            "Generate a targeted lesson plan to address the weakest grading criteria.",
            "Focus on the criteria with the lowest average scores.",
            "Include 3-5 structured activities with specific durations.",
            "Total lesson duration should be 45-90 minutes.",
            "Each activity must directly target one or more weak criteria by name.",
            "Include 3-5 discussion questions that probe the weak areas.",
            "End with a brief formative assessment suggestion.",
            "Add practical teacher_notes with tips for delivery.",
        ],
        "output_json_schema": {
            "title": "string",
            "duration": "string",
            "target_weaknesses": ["criterion names"],
            "learning_objectives": ["string"],
            "activities": [
                {
                    "name": "string",
                    "duration": "string",
                    "description": "string",
                    "addresses": ["criterion names"],
                    "materials": ["string"],
                }
            ],
            "discussion_questions": ["string"],
            "formative_assessment": "string",
            "teacher_notes": "string",
        },
    }
    return groq_client.call_llm_json_payload(payload, temperature=0.4)
