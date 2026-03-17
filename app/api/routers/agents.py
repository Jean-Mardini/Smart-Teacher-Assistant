<<<<<<< HEAD
from fastapi import APIRouter
from pydantic import BaseModel

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
from app.services.agents.chat_agent import run_chat

# ----------- RAG (MARK) -----------
from app.services.knowledge.retrieval import Retriever
=======
"""Routers exposing the different agents (summarizer, quiz, slides, etc.).

Currently empty – each agent will be wired here later.
"""

from fastapi import APIRouter
>>>>>>> origin/main


router = APIRouter()


<<<<<<< HEAD
# ---------------------------
# CHAT REQUEST MODEL
# ---------------------------
class ChatRequest(BaseModel):
    question: str


# ---------------------------
# INIT RETRIEVER (Mark's part)
# ---------------------------
retriever = Retriever()   # ⚠️ If error → adjust based on Mark


# ---------------------------
# DOCUMENT MOCK (TEMP)
# ---------------------------
async def get_document(doc_id: str):
    return {
        "document_id": "sample_pdf_001",
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

    return await run_quiz(doc, difficulty=req.difficulty)


# ---------------------------
# CHAT (RAG)
# ---------------------------
@router.post("/agents/chat")
async def chat(req: ChatRequest):

    result = await run_chat(
        question=req.question,
        retriever=retriever
    )

    return result
=======
>>>>>>> origin/main
