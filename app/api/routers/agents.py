"""angelas part"""

from fastapi import APIRouter, HTTPException, Response

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
from app.services.agents.quiz_export import quiz_to_moodle_xml
from app.services.agents.slide_export import slide_deck_to_pptx_bytes
from app.services.agents.slide_agent import run_slides
from app.services.agents.quiz_agent import run_quiz
from app.services.knowledge.indexing_pipeline import get_local_document_by_id

router = APIRouter()


async def get_document(doc_id: str):
    document = get_local_document_by_id(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    return document.model_dump()


async def get_documents(doc_ids: list[str]):
    return [await get_document(doc_id) for doc_id in doc_ids]


# ---------------------------
# SUMMARIZE
# ---------------------------
@router.post("/agents/summarize", response_model=SummaryResult)
async def summarize(req: SummaryRequest):
    try:
        docs = await get_documents(req.resolved_document_ids())
        return await run_summarizer(docs, length=req.length)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------
# SLIDES
# ---------------------------
@router.post("/agents/slides", response_model=SlideDeckResult)
async def slides(req: SlideRequest):
    doc = await get_document(req.document_id)
    return await run_slides(
        doc,
        n_slides=req.n_slides,
        generate_images=req.generate_images,
        image_style=req.image_style,
        max_generated_images=req.max_generated_images,
    )


@router.post("/agents/slides/export/pptx")
async def export_slides_pptx(req: SlideRequest):
    doc = await get_document(req.document_id)
    result = await run_slides(
        doc,
        n_slides=req.n_slides,
        generate_images=req.generate_images,
        image_style=req.image_style,
        max_generated_images=req.max_generated_images,
    )
    title = result.title or doc.get("title", "presentation")
    safe_title = "".join(ch if ch.isalnum() else "_" for ch in title).strip("_") or "presentation"
    pptx_bytes = slide_deck_to_pptx_bytes(result.model_dump())
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_title}.pptx"'
    }
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers=headers,
    )


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


@router.post("/agents/quiz/export/moodle-xml")
async def export_quiz_moodle_xml(req: QuizRequest):
    doc = await get_document(req.document_id)
    result = await run_quiz(
        doc,
        n_questions=req.n_questions,
        difficulty=req.difficulty,
    )
    title = doc.get("title", "quiz")
    safe_title = "".join(ch if ch.isalnum() else "_" for ch in title).strip("_") or "quiz"
    xml_text = quiz_to_moodle_xml(result.model_dump().get("quiz", []), category=title)
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_title}_quiz_moodle.xml"'
    }
    return Response(content=xml_text, media_type="application/xml", headers=headers)
