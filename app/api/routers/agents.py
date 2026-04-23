import os

from fastapi import APIRouter, HTTPException, Response

# ----------- MODELS -----------
from app.models.agents import (
    SummaryRequest,
    SummaryExportRequest,
    SlideRequest,
    QuizRequest,
    SummaryResult,
    SlideDeckResult,
    QuizResult,
)

# ----------- AGENTS -----------
from app.services.agents.summarizer_agent import run_summarizer
from app.services.agents.summary_export import (
    summary_payload_to_docx_bytes,
    summary_payload_to_pdf_bytes,
)
from app.services.agents.quiz_export import quiz_to_moodle_xml
from app.services.agents.slide_export import slide_deck_to_pptx_bytes
from app.services.agents.slide_agent import run_slides
from app.services.agents.quiz_agent import run_quiz
from app.services.knowledge.indexing_pipeline import get_local_document_by_id
from app.services.agents.slide_input import document_dict_for_slide_request
from app.services.agents.slide_image_generator import (
    active_image_model_label,
    get_slide_image_provider,
    slide_image_generation_status,
)

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


@router.post("/agents/summarize/export")
async def export_summary(req: SummaryExportRequest):
    """Download the current summary as Word or PDF (no re-run of the model)."""
    payload = req.model_dump(exclude={"format"})
    if req.format == "docx":
        body, filename = summary_payload_to_docx_bytes(payload)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        body, filename = summary_payload_to_pdf_bytes(payload)
        media = "application/pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=body, media_type=media, headers=headers)


# ---------------------------
# SLIDES
# ---------------------------
def _import_ok(module: str) -> bool:
    try:
        __import__(module)
    except ModuleNotFoundError:
        return False
    return True


@router.get("/agents/slides/image-status")
def slides_image_status():
    """Whether topic slide images will use HF / xAI / OpenAI or local placeholders (no secrets returned)."""
    provider = get_slide_image_provider()
    available, message = slide_image_generation_status()
    token_set = bool((os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or "").strip())
    return {
        "slide_image_provider": provider,
        "slide_images_available": available,
        "status_message": message,
        "active_model_label": active_image_model_label(),
        "hf_token_present": token_set,
        "slide_image_provider_env": (os.getenv("SLIDE_IMAGE_PROVIDER") or "").strip() or None,
        "huggingface_hub_installed": _import_ok("huggingface_hub"),
        "hf_image_model": (os.getenv("HF_IMAGE_MODEL") or "black-forest-labs/FLUX.1-schnell").strip(),
        "hf_inference_provider": (os.getenv("HF_INFERENCE_PROVIDER") or "auto").strip() or "auto",
        "tip_if_token_but_gradients": (
            "If hf_token_present is true but slides are only soft color washes: every HF call failed (check Uvicorn "
            "logs for 'HF text_to_image failed') — often 402 billing, model access, or timeout. Try HF_IMAGE_FALLBACK_MODEL "
            "or a smaller model, increase HF_INFERENCE_TIMEOUT, or add credit on https://huggingface.co/settings/billing"
            if token_set
            else None
        ),
    }


@router.post("/agents/slides", response_model=SlideDeckResult)
async def slides(req: SlideRequest):
    doc = await document_dict_for_slide_request(req)
    try:
        return await run_slides(
            doc,
            n_slides=req.n_slides,
            template=req.template,
            generate_images=req.generate_images,
            image_style=req.image_style,
            max_generated_images=req.max_generated_images,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/agents/slides/export/pptx")
async def export_slides_pptx(req: SlideRequest):
    doc = await document_dict_for_slide_request(req)
    try:
        result = await run_slides(
            doc,
            n_slides=req.n_slides,
            template=req.template,
            generate_images=req.generate_images,
            image_style=req.image_style,
            max_generated_images=req.max_generated_images,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    title = result.title or doc.get("title", "presentation")
    safe_title = "".join(ch if ch.isalnum() else "_" for ch in title).strip("_") or "presentation"
    deck_for_export = result.model_dump()
    # PPTX theme must follow the template the user selected in the request, even if the
    # model response omits or alters template metadata.
    deck_for_export["template"] = req.template
    deck_for_export.setdefault("template_used", req.template)
    pptx_bytes = slide_deck_to_pptx_bytes(deck_for_export)
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
        n_mcq=req.n_mcq,
        n_short_answer=req.n_short_answer,
        difficulty=req.difficulty,
    )


@router.post("/agents/quiz/export/moodle-xml")
async def export_quiz_moodle_xml(req: QuizRequest):
    doc = await get_document(req.document_id)
    result = await run_quiz(
        doc,
        n_mcq=req.n_mcq,
        n_short_answer=req.n_short_answer,
        difficulty=req.difficulty,
    )
    title = doc.get("title", "quiz")
    safe_title = "".join(ch if ch.isalnum() else "_" for ch in title).strip("_") or "quiz"
    xml_text = quiz_to_moodle_xml(result.model_dump().get("quiz", []), category=title)
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_title}_quiz_moodle.xml"'
    }
    return Response(content=xml_text, media_type="application/xml", headers=headers)
