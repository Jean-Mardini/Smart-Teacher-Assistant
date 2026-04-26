from __future__ import annotations
from typing import Any, Dict, List
from pydantic import BaseModel, Field


class AssignmentGenRequest(BaseModel):
    text: str = ""
    document_ids: List[str] = []
    difficulty: str = "medium"
    task_count: int = Field(default=5, ge=1, le=20)
    total_points: int = Field(default=100, ge=1, le=2000)


class ExamGenRequest(BaseModel):
    text: str = ""
    document_ids: List[str] = []
    difficulty: str = "medium"
    question_count: int = Field(default=10, ge=1, le=50)
    question_types: List[str] = ["short_answer"]
    total_points: int = Field(default=100, ge=1, le=2000)


class LessonPlanRequest(BaseModel):
    weak_criteria: List[Dict[str, Any]]
    class_average_pct: float
    context: str = ""


class GeneratedTask(BaseModel):
    number: int
    description: str
    points: int


class AssignmentGenResponse(BaseModel):
    title: str = ""
    objective: str = ""
    instructions: str = ""
    tasks: List[Dict[str, Any]] = []
    submission_requirements: str = ""
    rubric_items: List[Dict[str, Any]] = []


class GeneratedQuestion(BaseModel):
    number: int
    type: str
    question: str
    options: List[str] = []
    answer: str = ""
    points: int


class ExamGenResponse(BaseModel):
    title: str = ""
    instructions: str = ""
    duration: str = ""
    questions: List[Dict[str, Any]] = []
    rubric_items: List[Dict[str, Any]] = []


class LessonActivity(BaseModel):
    name: str
    duration: str
    description: str
    addresses: List[str] = []
    materials: List[str] = []


class LessonPlanResponse(BaseModel):
    title: str = ""
    duration: str = ""
    target_weaknesses: List[str] = []
    learning_objectives: List[str] = []
    activities: List[Dict[str, Any]] = []
    discussion_questions: List[str] = []
    formative_assessment: str = ""
    teacher_notes: str = ""
