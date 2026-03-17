from fastapi import APIRouter

# ----------- MODELS -----------
from app.models.agents import (
    SummaryRequest,
    SlideRequest,
    QuizRequest,
    SummaryResult,
    SlideDeckResult,
    QuizResult
)

# ----------- AGENTS -----------
from app.services.agents.summarizer_agent import run_summarizer
from app.services.agents.slide_agent import run_slides
from app.services.agents.quiz_agent import run_quiz

router = APIRouter()


# ---------------------------
# DOCUMENT MOCK (TEMP)
# ---------------------------
async def get_document(doc_id: str):
    return {
        "document_id": doc_id,
        "title": "AI Teacher Assistant",
        "metadata": {
            "filename": "sample.pdf",
            "filetype": "pdf",
            "total_pages": 3
        },
        "sections": [
            {
                "section_id": "sec_1",
                "heading": "Introduction",
                "level": 1,
                "page_start": 1,
                "page_end": 1,
                "text": "This document introduces an AI-powered teacher assistant."
            },
            {
                "section_id": "sec_2",
                "heading": "Methods",
                "level": 1,
                "page_start": 1,
                "page_end": 2,
                "text": "The system processes documents and generates summaries, slides and quizzes."
            }
        ],
        "tables": [],
        "images": []
    }


# ---------------------------
# SUMMARIZE
# ---------------------------
@router.post("/agents/summarize", response_model=SummaryResult)
async def summarize(req: SummaryRequest):
    doc = await get_document(req.document_id)
    return await run_summarizer(doc, length=req.length)


# ---------------------------
# SLIDES
# ---------------------------
@router.post("/agents/slides", response_model=SlideDeckResult)
async def slides(req: SlideRequest):
    doc = await get_document(req.document_id)
    return await run_slides(doc, n_slides=req.n_slides)


# ---------------------------
# QUIZ
# ---------------------------
@router.post("/agents/quiz", response_model=QuizResult)
async def quiz(req: QuizRequest):
    doc = await get_document(req.document_id)
    return await run_quiz(
        doc,
        n_questions=req.n_questions,
        difficulty=req.difficulty
    )