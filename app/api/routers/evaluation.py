"""Routers for rubric generation, grading, and history (Kristy's Flexible Grader)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.models.evaluation import (
    BatchGradeRequest,
    BatchGradeResponse,
    EvaluationConfigResponse,
    EvaluationConfigUpdateRequest,
    EvaluationPresetSaveRequest,
    EvaluationPresetsResponse,
    EvaluationStatusResponse,
    ExportBatchRequest,
    ExportSingleRequest,
    GradeSubmissionRequest,
    GradeSubmissionResponse,
    HistoryListResponse,
    HistoryRecordUpdateRequest,
    ParsedUploadListResponse,
    RubricFromTextRequest,
    RubricGenerationResponse,
    SourceTextRequest,
    SourceTextResponse,
)
from app.services.evaluation import flexible_grader as fg
from app.services.llm.groq_client import invalidate_config_cache

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_key(secret: str) -> str:
    key = (secret or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


def _slugify(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip()).strip("._-")
    return clean or "evaluation"


def _compose_text(text: str = "", document_ids: List[str] | None = None) -> Dict[str, Any]:
    return fg.compose_text_from_sources(
        manual_text=text or "",
        document_ids=document_ids or [],
    )


def _plain_response(content: str | bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@router.get("/status", response_model=EvaluationStatusResponse)
async def evaluation_status() -> EvaluationStatusResponse:
    return EvaluationStatusResponse()


@router.get("/config", response_model=EvaluationConfigResponse)
async def evaluation_config() -> EvaluationConfigResponse:
    cfg = await asyncio.to_thread(fg.load_config)
    key = str(cfg.get("GROQ_API_KEY", "")).strip()
    model = str(cfg.get("GROQ_MODEL", "")).strip()
    return EvaluationConfigResponse(
        has_api_key=bool(key),
        api_key_preview=_mask_key(key),
        model=model or fg.DEFAULT_MODEL,
    )


@router.put("/config", response_model=EvaluationConfigResponse)
async def update_evaluation_config(body: EvaluationConfigUpdateRequest) -> EvaluationConfigResponse:
    cfg = await asyncio.to_thread(fg.load_config)

    if body.groq_api_key is not None:
        key = body.groq_api_key.strip()
        if key:
            cfg["GROQ_API_KEY"] = key
        else:
            cfg.pop("GROQ_API_KEY", None)

    if body.model is not None:
        model = body.model.strip()
        if model:
            cfg["GROQ_MODEL"] = model
        else:
            cfg.pop("GROQ_MODEL", None)

    await asyncio.to_thread(fg.save_config, cfg)
    invalidate_config_cache()

    saved_key = str(cfg.get("GROQ_API_KEY", "")).strip()
    saved_model = str(cfg.get("GROQ_MODEL", "")).strip()
    return EvaluationConfigResponse(
        has_api_key=bool(saved_key),
        api_key_preview=_mask_key(saved_key),
        model=saved_model or fg.DEFAULT_MODEL,
    )


# ---------------------------------------------------------------------------
# Text resolution
# ---------------------------------------------------------------------------

@router.post("/resolve-text", response_model=SourceTextResponse)
async def resolve_source_text(body: SourceTextRequest) -> SourceTextResponse:
    resolved = await asyncio.to_thread(_compose_text, body.text, body.document_ids)
    return SourceTextResponse(
        text=str(resolved.get("text", "")),
        documents=list(resolved.get("documents", [])),
    )


# ---------------------------------------------------------------------------
# Rubric generation — standard (blocking) endpoints
# ---------------------------------------------------------------------------

@router.post("/rubric/from-assignment", response_model=RubricGenerationResponse)
async def rubric_from_assignment(body: RubricFromTextRequest) -> Dict[str, Any]:
    resolved = await asyncio.to_thread(_compose_text, body.text, body.document_ids)
    text = str(resolved.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Provide assignment text or at least one document.")
    result = await asyncio.to_thread(fg.generate_items_from_assignment, text, body.total_points)
    return result


@router.post("/rubric/from-teacher-key", response_model=RubricGenerationResponse)
async def rubric_from_teacher_key(body: RubricFromTextRequest) -> Dict[str, Any]:
    resolved = await asyncio.to_thread(_compose_text, body.text, body.document_ids)
    text = str(resolved.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Provide teacher-key text or at least one document.")
    result = await asyncio.to_thread(fg.generate_items_from_teacher_key, text, body.total_points)
    return result


# ---------------------------------------------------------------------------
# Rubric generation — streaming SSE endpoints
# Stream status events while the LLM call runs, then emit the full result.
# Event shapes:
#   {"status": "resolving", "message": "…"}
#   {"status": "generating", "message": "…"}
#   {"done": true, "rubric_title": …, "summary": […], "items": […]}
#   {"error": "…"}
# ---------------------------------------------------------------------------

async def _stream_rubric(
    body: RubricFromTextRequest,
    generator_fn,
) -> AsyncGenerator[str, None]:
    try:
        yield _sse({"status": "resolving", "message": "Resolving source documents…"})
        resolved = await asyncio.to_thread(_compose_text, body.text, body.document_ids)
        text = str(resolved.get("text", "")).strip()
        if not text:
            yield _sse({"error": "Provide assignment text or at least one document."})
            return

        char_count = len(text)
        yield _sse({
            "status": "generating",
            "message": f"Sending {char_count:,} characters to the AI model…",
        })

        result = await asyncio.to_thread(generator_fn, text, body.total_points)
        yield _sse({"done": True, **result})

    except Exception as exc:
        logger.warning("Streaming rubric generation failed", exc_info=True)
        yield _sse({"error": str(exc)})


@router.post("/rubric/from-assignment/stream")
async def rubric_from_assignment_stream(body: RubricFromTextRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_rubric(body, fg.generate_items_from_assignment),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/rubric/from-teacher-key/stream")
async def rubric_from_teacher_key_stream(body: RubricFromTextRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_rubric(body, fg.generate_items_from_teacher_key),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

@router.post("/grade", response_model=GradeSubmissionResponse)
async def grade_submission(body: GradeSubmissionRequest) -> GradeSubmissionResponse:
    submission = str(
        (await asyncio.to_thread(_compose_text, body.submission_text, body.submission_document_ids)).get("text", "")
    ).strip()
    if not submission:
        raise HTTPException(status_code=400, detail="Provide submission text or at least one submission document.")
    if not body.items:
        raise HTTPException(status_code=400, detail="items must be a non-empty rubric.")
    if fg.requires_reference_material(body.items) and not ((body.reference_text or "").strip() or (body.reference_document_ids or [])):
        raise HTTPException(
            status_code=400,
            detail="Please upload, select, or paste reference material before grading because one or more criteria use reference or hybrid grounding.",
        )

    teacher_key_text = str(
        (await asyncio.to_thread(_compose_text, body.teacher_key_text, body.teacher_key_document_ids)).get("text", "")
    ).strip()

    result = await asyncio.to_thread(
        fg.grade_submission_fast,
        submission_text=submission,
        items=body.items,
        teacher_key_text=teacher_key_text,
        reference_document_ids=body.reference_document_ids or None,
        reference_text=str(body.reference_text or "").strip(),
    )

    record = fg.build_result_record(
        body.result_title,
        result,
        submission,
        history_type="single",
    )
    if body.save_history:
        await asyncio.to_thread(fg.append_history, record)

    return GradeSubmissionResponse(
        overall_score=float(result.get("overall_score", 0)),
        overall_out_of=int(result.get("overall_out_of", 0)),
        items_results=list(result.get("items_results", [])),
        record=record,
    )



@router.post("/grade/batch", response_model=BatchGradeResponse)
async def grade_batch(body: BatchGradeRequest) -> BatchGradeResponse:
    if not body.items:
        raise HTTPException(status_code=400, detail="items must be a non-empty rubric.")
    if not body.submissions:
        raise HTTPException(status_code=400, detail="submissions must be provided.")
    if fg.requires_reference_material(body.items) and not ((body.reference_text or "").strip() or (body.reference_document_ids or [])):
        raise HTTPException(
            status_code=400,
            detail="Please upload, select, or paste reference material before grading because one or more criteria use reference or hybrid grounding.",
        )

    teacher_key_text = str(
        (await asyncio.to_thread(_compose_text, body.teacher_key_text, body.teacher_key_document_ids)).get("text", "")
    ).strip()

    batch_name = str(body.batch_name or "").strip()
    batch_created_at = fg.now_iso()
    raw_records: List[Dict[str, Any]] = []
    skipped = 0
    for submission in body.submissions:
        submission_text = str(
            (await asyncio.to_thread(_compose_text, submission.submission_text, submission.submission_document_ids)).get("text", "")
        ).strip()
        if not submission_text:
            skipped += 1
            logger.warning("Skipping submission '%s': no text resolved", submission.title)
            continue

        result = await asyncio.to_thread(
            fg.grade_submission_fast,
            submission_text=submission_text,
            items=body.items,
            teacher_key_text=teacher_key_text,
            reference_document_ids=body.reference_document_ids or None,
            reference_text=str(body.reference_text or "").strip(),
        )
        raw_records.append(
            fg.build_result_record(
                submission.title,
                result,
                submission_text,
                history_type="batch_submission",
                batch_name=batch_name,
                batch_created_at=batch_created_at,
            )
        )

    raw_records.sort(key=lambda item: float(item.get("overall_score", 0)), reverse=True)
    final_batch_name = batch_name or f"Batch {batch_created_at}"
    batch_id = fg.history_batch_id(final_batch_name, raw_records) if raw_records else ""

    records: List[Dict[str, Any]] = []
    for index, record in enumerate(raw_records, start=1):
        updated = {
            **record,
            "batch_id": batch_id,
            "batch_name": final_batch_name,
            "batch_size": len(raw_records),
            "batch_rank": index,
            "batch_created_at": batch_created_at,
        }
        if body.save_history:
            await asyncio.to_thread(fg.append_history, updated)
        records.append(updated)

    stats = fg.build_history_stats(records, fg.build_history_batches(records))
    return BatchGradeResponse(records=records, batch_id=batch_id, batch_name=final_batch_name, stats=stats)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

@router.get("/presets", response_model=EvaluationPresetsResponse)
async def list_evaluation_presets() -> EvaluationPresetsResponse:
    return EvaluationPresetsResponse(presets=await asyncio.to_thread(fg.load_presets))


@router.put("/presets/{name}", response_model=EvaluationPresetsResponse)
async def save_evaluation_preset(name: str, body: EvaluationPresetSaveRequest) -> EvaluationPresetsResponse:
    preset_name = name.strip()
    if not preset_name:
        raise HTTPException(status_code=400, detail="Preset name is required.")
    if not body.items:
        raise HTTPException(status_code=400, detail="Preset items cannot be empty.")

    presets = await asyncio.to_thread(fg.load_presets)
    presets[preset_name] = {
        "items": body.items,
        "saved_at": fg.now_iso(),
        "total_points": body.total_points,
        "origin": (body.origin or "assignment").strip() or "assignment",
    }
    await asyncio.to_thread(fg.save_presets, presets)
    return EvaluationPresetsResponse(presets=presets)


@router.delete("/presets/{name}", response_model=EvaluationPresetsResponse)
async def delete_evaluation_preset(name: str) -> EvaluationPresetsResponse:
    presets = await asyncio.to_thread(fg.load_presets)
    presets.pop(name, None)
    await asyncio.to_thread(fg.save_presets, presets)
    return EvaluationPresetsResponse(presets=presets)


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

@router.post("/uploads/parse", response_model=ParsedUploadListResponse)
async def parse_uploaded_evaluation_files(files: list[UploadFile] = File(...)) -> ParsedUploadListResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")
    parsed = await asyncio.to_thread(fg.parse_uploaded_files, files)
    return ParsedUploadListResponse(items=parsed)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/history", response_model=HistoryListResponse)
async def evaluation_history(
    limit: int = Query(250, ge=1, le=2000),
    date_from: str = Query("", description="Inclusive lower date bound in YYYY-MM-DD."),
    date_to: str = Query("", description="Inclusive upper date bound in YYYY-MM-DD."),
    search: str = Query("", description="Free-text filter against titles, batch names, ids, and timestamps."),
    history_type: str = Query("all", description="all | single | batch"),
) -> HistoryListResponse:
    view = await asyncio.to_thread(
        fg.load_history_view,
        limit,
        date_from,
        date_to,
        search,
        history_type,
    )
    return HistoryListResponse(
        records=list(view.get("records", [])),
        batches=list(view.get("batches", [])),
        stats=dict(view.get("stats", {})),
    )


@router.delete("/history")
async def clear_evaluation_history() -> Dict[str, str]:
    await asyncio.to_thread(fg.clear_history)
    return {"status": "cleared"}


@router.put("/history/{record_id}")
async def update_evaluation_history_record(record_id: str, body: HistoryRecordUpdateRequest) -> Dict[str, Any]:
    updated = await asyncio.to_thread(fg.update_history_record, record_id, body.record)
    if updated is None:
        raise HTTPException(status_code=404, detail="History record not found.")
    return {"record": updated}


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

@router.post("/export/single/{fmt}")
async def export_single_report(fmt: str, body: ExportSingleRequest) -> Response:
    record = body.record or {}
    record_id = _slugify(str(record.get("id", "result")))

    if fmt == "txt":
        return _plain_response(
            await asyncio.to_thread(fg.export_single_report, record),
            "text/plain; charset=utf-8",
            f"single_report_{record_id}.txt",
        )
    if fmt == "html":
        return _plain_response(
            await asyncio.to_thread(fg.build_single_report_html, record),
            "text/html; charset=utf-8",
            f"single_report_{record_id}.html",
        )
    if fmt == "docx":
        return _plain_response(
            await asyncio.to_thread(fg.build_docx_report, record),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"single_report_{record_id}.docx",
        )
    raise HTTPException(status_code=400, detail="fmt must be txt, html, or docx.")


@router.post("/export/batch/{fmt}")
async def export_batch_report(fmt: str, body: ExportBatchRequest) -> Response:
    records = body.records or []
    if fmt == "txt":
        return _plain_response(
            await asyncio.to_thread(fg.export_batch_report, records),
            "text/plain; charset=utf-8",
            "batch_report.txt",
        )
    if fmt == "html":
        return _plain_response(
            await asyncio.to_thread(fg.build_batch_report_html, records),
            "text/html; charset=utf-8",
            "batch_report.html",
        )
    if fmt == "docx":
        return _plain_response(
            await asyncio.to_thread(fg.build_batch_docx_report, records),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "batch_report.docx",
        )
    raise HTTPException(status_code=400, detail="fmt must be txt, html, or docx.")
