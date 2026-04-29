from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error, request
import uuid

# Load `.env` from repo root (same as FastAPI) so HF_TOKEN / keys exist if anything imports app code locally.
_PROJECT_ROOT = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv

    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

import streamlit as st

from app.services.agents.quiz_export import quiz_to_moodle_xml
from app.services.agents.slide_export import slide_deck_to_pptx_bytes


DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"


def api_get(base_url: str, path: str) -> Any:
    req = request.Request(f"{base_url}{path}", method="GET")
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def api_post(base_url: str, path: str, payload: dict[str, Any]) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base_url}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def api_post_multipart(base_url: str, path: str, files: list[tuple[str, bytes, str]]) -> Any:
    boundary = f"----SmartTeacherBoundary{uuid.uuid4().hex}"
    body = bytearray()

    for filename, content, content_type in files:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = request.Request(
        f"{base_url}{path}",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def safe_api_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return None, f"HTTP {exc.code}: {detail}"
    except Exception as exc:
        return None, str(exc)


def _slide_image_lookup(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        image["image_id"]: image
        for image in result.get("image_catalog", [])
        if image.get("image_id")
    }


def render_slide_images(result: dict[str, Any], slide: dict[str, Any]) -> None:
    image_lookup = _slide_image_lookup(result)
    assets: list[str] = []
    captions: list[str] = []

    for image_id in slide.get("image_refs", []):
        image = image_lookup.get(image_id)
        asset_path = image.get("asset_path") if image else None
        if not asset_path or not Path(asset_path).exists():
            continue
        assets.append(asset_path)
        source = image.get("source", "document")
        caption = image.get("caption") or image_id
        captions.append(f"{caption} ({source})")

    if assets:
        st.image(assets, caption=captions, use_container_width=True)


# Maps API slide template id -> Streamlit preview layout name used by render_slide_deck.
_SLIDES_PREVIEW_LAYOUT = {
    "academic_default": "Classic",
    "minimal_clean": "Two-Column",
    "workshop_interactive": "Lecture Notes",
    "executive_summary": "Spotlight",
    "deep_technical": "Classic",
    "story_visual": "Spotlight",
}


def render_slide_deck(result: dict[str, Any], template: str) -> None:
    st.markdown(f"### {result['title']}")

    if template == "Classic":
        for index, slide in enumerate(result["slides"], start=1):
            with st.container(border=True):
                st.markdown(f"**Slide {index}: {slide['slide_title']}**")
                for bullet in slide["bullets"]:
                    st.write(f"- {bullet}")
                render_slide_images(result, slide)
                if slide.get("speaker_notes"):
                    st.caption(slide["speaker_notes"])
        return

    if template == "Two-Column":
        for index, slide in enumerate(result["slides"], start=1):
            left, right = st.columns([1.05, 1.95], gap="medium")
            with left:
                st.markdown(
                    f"""
                    <div style="
                        background: linear-gradient(155deg, #ff6b57 0%, #ff9f43 100%);
                        border-radius: 20px;
                        padding: 24px;
                        min-height: 220px;
                        color: white;
                    ">
                        <div style="font-size: 0.85rem; letter-spacing: 0.08em; opacity: 0.85;">SLIDE {index}</div>
                        <div style="font-size: 1.85rem; font-weight: 800; line-height: 1.1; margin-top: 16px;">
                            {slide['slide_title']}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with right:
                bullets_html = "".join(
                    f"<li style='margin-bottom: 10px;'>{bullet}</li>"
                    for bullet in slide["bullets"]
                )
                notes_html = ""
                if slide.get("speaker_notes"):
                    notes_html = (
                        "<div style='margin-top: 16px; color: #9ca3af; font-size: 0.95rem;'>"
                        f"{slide['speaker_notes']}"
                        "</div>"
                    )
                st.markdown(
                    f"""
                    <div style="
                        background: #141821;
                        border: 1px solid #303746;
                        border-radius: 20px;
                        padding: 24px 28px;
                        min-height: 220px;
                    ">
                        <ul style="margin: 0; padding-left: 20px; font-size: 1.08rem; line-height: 1.6;">
                            {bullets_html}
                        </ul>
                        {notes_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                render_slide_images(result, slide)
        return

    if template == "Spotlight":
        for index, slide in enumerate(result["slides"], start=1):
            bullets_html = "".join(
                f"""
                <div style="
                    background: rgba(255,255,255,0.06);
                    border: 1px solid rgba(255,255,255,0.09);
                    border-radius: 14px;
                    padding: 14px 16px;
                ">{bullet}</div>
                """
                for bullet in slide["bullets"]
            )
            st.markdown(
                f"""
                <div style="
                    background:
                        radial-gradient(circle at top right, rgba(255,107,87,0.28), transparent 30%),
                        linear-gradient(180deg, #111722 0%, #0d1017 100%);
                    border: 1px solid #2d3340;
                    border-radius: 24px;
                    padding: 28px;
                    margin-bottom: 20px;
                ">
                    <div style="color: #ff9f43; font-size: 0.9rem; letter-spacing: 0.08em;">SLIDE {index}</div>
                    <div style="font-size: 2rem; font-weight: 800; margin: 8px 0 18px 0;">
                        {slide['slide_title']}
                    </div>
                    <div style="
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                        gap: 12px;
                    ">
                        {bullets_html}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_slide_images(result, slide)
            if slide.get("speaker_notes"):
                st.caption(slide["speaker_notes"])
        return

    if template == "Lecture Notes":
        for index, slide in enumerate(result["slides"], start=1):
            main_point = slide["bullets"][0] if slide["bullets"] else ""
            extra_points = slide["bullets"][1:]
            st.markdown(
                f"""
                <div style="
                    background: #f6efe2;
                    color: #241c15;
                    border-radius: 20px;
                    padding: 26px;
                    margin-bottom: 18px;
                    border-left: 8px solid #cc5f35;
                ">
                    <div style="font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.08em; color: #8a4a2f;">
                        Lecture Slide {index}
                    </div>
                    <div style="font-size: 1.9rem; font-weight: 800; margin-top: 8px;">
                        {slide['slide_title']}
                    </div>
                    <div style="margin-top: 16px; font-size: 1.08rem;">
                        <strong>Main point:</strong> {main_point}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for bullet in extra_points:
                st.write(f"- {bullet}")
            render_slide_images(result, slide)
            if slide.get("speaker_notes"):
                st.caption(slide["speaker_notes"])


st.set_page_config(
    page_title="Smart Teacher Assistant Demo",
    page_icon="📚",
    layout="wide",
)

st.title("Smart Teacher Assistant")
st.caption("Angela's demo: summary, slides, quiz, and chatbot")

with st.sidebar:
    st.header("Backend")
    backend_url = st.text_input("FastAPI URL", value=DEFAULT_BACKEND_URL)

    health, health_error = safe_api_call(api_get, backend_url, "/health")
    if health_error:
        st.error("Backend unavailable")
        st.caption(health_error)
    else:
        st.success(f"Backend status: {health.get('status', 'ok')}")

    st.header("Knowledge Base")
    uploaded_files = st.file_uploader(
        "Upload from device",
        type=["txt", "md", "json", "pdf", "docx", "pptx"],
        accept_multiple_files=True,
    )
    if st.button("Upload Documents", use_container_width=True):
        if not uploaded_files:
            st.warning("Choose at least one file to upload.")
        else:
            multipart_files = [
                (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    uploaded_file.type or "application/octet-stream",
                )
                for uploaded_file in uploaded_files
            ]
            result, upload_error = safe_api_call(
                api_post_multipart,
                backend_url,
                "/documents/upload",
                multipart_files,
            )
            if upload_error:
                st.error(upload_error)
            else:
                st.success(f"Uploaded {len(result)} document(s). Reindex to use them in RAG/chat.")
                st.rerun()

    docs, docs_error = safe_api_call(api_get, backend_url, "/documents/local")
    if docs_error:
        st.warning("Could not load local documents")
        st.caption(docs_error)
        docs = []

    doc_options = {
        f"{doc['title']} ({doc['filetype']})": doc["document_id"]
        for doc in docs
    }

    rag_status, rag_error = safe_api_call(api_get, backend_url, "/rag/status")
    current_chunk_size = 900
    current_chunk_overlap = 150
    if rag_status and rag_status.get("chunking"):
        current_chunk_size = rag_status["chunking"].get("chunk_size", current_chunk_size)
        current_chunk_overlap = rag_status["chunking"].get("chunk_overlap", current_chunk_overlap)

    st.caption("RAG Chunking")
    rag_chunk_size = st.number_input(
        "Chunk size",
        min_value=200,
        max_value=5000,
        value=current_chunk_size,
        step=100,
    )
    rag_chunk_overlap = st.number_input(
        "Chunk overlap",
        min_value=0,
        max_value=2000,
        value=current_chunk_overlap,
        step=50,
    )

    if st.button("Reindex Documents", use_container_width=True):
        _, reindex_error = safe_api_call(
            api_post,
            backend_url,
            "/rag/reindex",
            {
                "chunk_size": int(rag_chunk_size),
                "chunk_overlap": int(rag_chunk_overlap),
            },
        )
        if reindex_error:
            st.error(reindex_error)
        else:
            st.success("Reindex completed")
    if rag_status:
        st.caption(f"Indexed docs: {rag_status['indexed_documents']}")
        st.caption(f"Indexed chunks: {rag_status['indexed_chunks']}")
        if rag_status.get("chunking"):
            st.caption(
                f"Chunking: {rag_status['chunking']['chunk_size']} / overlap {rag_status['chunking']['chunk_overlap']}"
            )
    elif rag_error:
        st.caption(rag_error)

if not doc_options:
    st.info(
        "Add files to `data/knowledge_base`, start FastAPI, then reindex to begin the demo."
    )
    st.stop()

selected_labels = st.sidebar.multiselect(
    "Choose one or more documents",
    list(doc_options.keys()),
    default=list(doc_options.keys())[:1],
)
if not selected_labels:
    st.warning("No document is currently selected. Check that the backend is running and documents are loaded.")
    st.stop()

selected_document_ids = [doc_options[label] for label in selected_labels if label in doc_options]
primary_document_id = selected_document_ids[0]

summary_tab, slides_tab, quiz_tab, chat_tab = st.tabs(
    ["Summarizer", "Slides", "Quiz", "Chatbot"]
)

with summary_tab:
    st.subheader("Document Summary")
    summary_length = st.selectbox("Summary length", ["short", "medium", "long"], index=1)
    st.caption(
        "Up to 10 documents per run; large decks use parallel chunking and optional RAG (see backend .env.example)."
    )

    if st.button("Generate Summary", type="primary", key="summary_button"):
        with st.spinner("Generating summary..."):
            payload = {"length": summary_length}
            if len(selected_document_ids) == 1:
                payload["document_id"] = primary_document_id
            else:
                payload["document_ids"] = selected_document_ids

            result, api_error = safe_api_call(
                api_post,
                backend_url,
                "/agents/summarize",
                payload,
            )

        if api_error:
            st.error(api_error)
        else:
            st.markdown("### Summary")
            st.write(result["summary"])

            if result.get("key_points"):
                st.markdown("### Key Points")
                for point in result["key_points"]:
                    st.write(f"- {point}")

            if result.get("action_items"):
                st.markdown("### Action Items")
                for item in result["action_items"]:
                    st.write(f"- {item}")

            if result.get("formulas"):
                st.markdown("### Formulas")
                for expr in result["formulas"]:
                    st.code(expr, language=None)

            st.markdown("### Glossary")
            if result.get("glossary"):
                for item in result["glossary"]:
                    st.write(f"**{item['term']}**: {item['definition']}")
            else:
                st.caption("No glossary terms were identified for this summary.")

            if result.get("source_documents"):
                st.markdown("### Source Documents")
                for title in result["source_documents"]:
                    st.write(f"- {title}")

            stats = []
            if result.get("total_pages"):
                stats.append(f"pages: {result['total_pages']}")
            if result.get("chunk_count"):
                stats.append(f"summary chunks: {result['chunk_count']}")
            if stats:
                st.caption(" | ".join(stats))

            if result.get("image_notes"):
                st.markdown("### Image Notes")
                for note in result["image_notes"]:
                    st.write(f"- {note}")

            if result.get("processing_notes"):
                st.markdown("### Processing Notes")
                for note in result["processing_notes"]:
                    st.write(f"- {note}")

            with st.expander("JSON Structure", expanded=False):
                st.json(result)

with slides_tab:
    st.subheader("Slide Generation")
    st.caption("Create with AI: library document, pasted text, one-line prompt, or URL import (same API as the web app).")
    slide_source_mode = st.radio(
        "How to start",
        ["Library document", "Paste text", "One-line prompt", "URL import"],
        horizontal=True,
        key="slides_source_mode",
    )
    top_left, top_right = st.columns([1, 1])
    with top_left:
        n_slides = st.slider("Number of slides", min_value=1, max_value=20, value=5)
    with top_right:
        slide_template = st.selectbox(
            "Slide template (LLM prompt)",
            [
                ("academic_default", "Default (modern deck)"),
                ("minimal_clean", "Minimal & clean"),
                ("workshop_interactive", "Workshop / interactive"),
                ("executive_summary", "Executive summary"),
                ("deep_technical", "Technical deep-dive"),
                ("story_visual", "Story / keynote"),
            ],
            format_func=lambda x: x[1],
            index=0,
        )
    slide_image_style = st.selectbox(
        "AI image art style (topic-based; one image per slide when an image API key is set on the backend)",
        [
            "vector_science",
            "illustration",
            "photo",
            "abstract",
            "3d",
            "line_art",
            "diagram",
        ],
        format_func=lambda x: {
            "vector_science": "Science deck (vector)",
            "illustration": "Illustration",
            "photo": "Photo",
            "abstract": "Abstract",
            "3d": "3D",
            "line_art": "Line art",
            "diagram": "Diagram / infographic",
        }.get(x, x),
        index=0,
    )
    st.caption(
        "Images are generated from each slide’s title and bullets (not from the slide layout). "
        "Set HF_TOKEN, XAI_API_KEY, or OPENAI_API_KEY on the API server for real renders; otherwise placeholders may apply."
    )

    slides_payload: dict = {"n_slides": n_slides, "template": slide_template[0], "image_style": slide_image_style}
    if slide_source_mode == "Library document":
        slides_payload["document_id"] = primary_document_id
    elif slide_source_mode == "Paste text":
        pasted = st.text_area("Paste notes or outline", height=220, key="slides_paste_body")
        title_opt = st.text_input("Deck title (optional)", "", key="slides_paste_title")
        slides_payload["source_text"] = pasted or ""
        if title_opt.strip():
            slides_payload["source_title"] = title_opt.strip()
    elif slide_source_mode == "One-line prompt":
        slides_payload["source_text"] = st.text_input("One-line prompt", "", key="slides_prompt_line") or ""
    else:
        url = st.text_input("Page URL (https…)", "", key="slides_import_url")
        title_opt = st.text_input("Deck title (optional)", "", key="slides_url_title")
        slides_payload["source_url"] = url or ""
        if title_opt.strip():
            slides_payload["source_title"] = title_opt.strip()

    if st.button("Generate Slides", type="primary", key="slides_button"):
        with st.spinner("Generating slides..."):
            result, api_error = safe_api_call(
                api_post,
                backend_url,
                "/agents/slides",
                slides_payload,
            )

        if api_error:
            st.error(api_error)
        else:
            st.session_state.slides_result = result
            st.session_state.slides_document_id = primary_document_id
            st.session_state.slides_source_mode_saved = slide_source_mode

    if "slides_result" in st.session_state:
        lib_mismatch = st.session_state.get("slides_source_mode_saved") == "Library document" and (
            st.session_state.get("slides_document_id") != primary_document_id
        )
        if lib_mismatch:
            st.info("Generate slides for the newly selected document to preview them here.")
        else:
            result = st.session_state.slides_result
            proc = result.get("processing_notes") or []
            local_ok = any(
                ("Attached" in str(n) and "local slide illustration" in str(n))
                or "local_placeholder" in str(n)
                or ("not AI-generated" in str(n) and "PPTX" in str(n))
                for n in proc
            )
            if not local_ok and any(
                "No AI slide" in str(n)
                or "No slide images were generated" in str(n)
                or "OPENAI_API_KEY" in str(n)
                or "XAI_API_KEY" in str(n)
                or "HF_TOKEN" in str(n)
                or "HUGGING_FACE" in str(n)
                or "huggingface_hub" in str(n)
                or "AI image generation failed" in str(n)
                for n in proc
            ):
                st.warning(
                    "Slide text was generated, but **API image models did not attach**. "
                    "Set `HF_TOKEN`, `XAI_API_KEY`, or `OPENAI_API_KEY` and restart the API, "
                    "or leave keys unset for **local placeholder** images (default). Details under Processing Notes."
                )
            preview = _SLIDES_PREVIEW_LAYOUT.get(slide_template[0], "Classic")
            render_slide_deck(result, preview)

            export_deck = dict(result)
            export_deck.setdefault("template_used", slide_template[0])
            export_deck.setdefault("template", slide_template[0])
            pptx_export = slide_deck_to_pptx_bytes(export_deck)
            pptx_name = f"{primary_document_id}_slides.pptx"

            st.download_button(
                "Download PowerPoint (.pptx)",
                data=pptx_export,
                file_name=pptx_name,
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                key="download_slides_pptx",
            )

            if result.get("image_notes"):
                st.markdown("### Image Notes")
                for note in result["image_notes"]:
                    st.write(f"- {note}")

            if result.get("processing_notes"):
                st.markdown("### Processing Notes")
                for note in result["processing_notes"]:
                    st.write(f"- {note}")

            with st.expander("JSON Structure", expanded=False):
                st.json(result)

with quiz_tab:
    st.subheader("Quiz Generation")
    st.caption("Quiz generation uses the first selected document.")
    qc1, qc2, qc3 = st.columns(3)
    with qc1:
        n_mcq = st.slider("Multiple choice (MCQ)", min_value=0, max_value=15, value=3)
    with qc2:
        n_true_false = st.slider("True / false", min_value=0, max_value=15, value=0)
    with qc3:
        n_short_answer = st.slider("Short answer (sentence)", min_value=0, max_value=15, value=2)
    if n_mcq + n_short_answer + n_true_false < 1:
        st.warning("Choose at least one question (MCQ, true/false, and/or short answer).")
    difficulty = st.selectbox("Difficulty", ["easy", "medium", "hard"], index=1)

    if st.button("Generate Quiz", type="primary", key="quiz_button"):
        if n_mcq + n_short_answer + n_true_false < 1:
            st.error("Need at least one MCQ, true/false, or short-answer question.")
        else:
            with st.spinner("Generating quiz..."):
                result, api_error = safe_api_call(
                    api_post,
                    backend_url,
                    "/agents/quiz",
                    {
                        "document_id": primary_document_id,
                        "n_mcq": n_mcq,
                        "n_short_answer": n_short_answer,
                        "n_true_false": n_true_false,
                        "difficulty": difficulty,
                    },
                )

            if api_error:
                st.error(api_error)
            else:
                st.session_state.quiz_result = result
                st.session_state.quiz_document_id = primary_document_id
                st.session_state.quiz_document_label = selected_labels[0]

                for index, question in enumerate(result["quiz"], start=1):
                    with st.container(border=True):
                        st.markdown(f"**Q{index}. {question['question']}**")
                        if question["type"] == "mcq":
                            for option in question.get("options", []):
                                st.write(option)
                        elif question["type"] == "true_false":
                            for option in question.get("options", []):
                                st.write(option)
                        st.write(f"Answer: {question.get('answer_text', '')}")
                        st.caption(question.get("explanation", ""))

                with st.expander("JSON Structure", expanded=False):
                    st.json(result)

    if "quiz_result" in st.session_state:
        if st.session_state.get("quiz_document_id") != primary_document_id:
            st.info("Generate a quiz for the newly selected document to export it.")
        else:
            xml_export = quiz_to_moodle_xml(
                st.session_state.quiz_result.get("quiz", []),
                category=st.session_state.get("quiz_document_label", "Quiz"),
            )
            st.download_button(
                "Download Moodle XML",
                data=xml_export,
                file_name=f"{primary_document_id}_quiz_moodle.xml",
                mime="application/xml",
                key="download_moodle_xml",
            )

with chat_tab:
    st.subheader("Chat with Documents")
    st.caption("Chat can use indexed sections, tables, and image descriptions when they exist in the indexed data.")
    chat_length = st.selectbox(
        "Answer length",
        ["short", "medium", "long"],
        index=1,
        key="chat_length",
    )
    chat_top_k = st.slider("Retrieved chunks (top_k)", min_value=1, max_value=10, value=3)
    chat_temperature = st.slider("Temperature", min_value=0.0, max_value=1.5, value=0.2, step=0.1)

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    question = st.chat_input("Ask a question about the indexed documents")
    if question:
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.write(question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result, api_error = safe_api_call(
                    api_post,
                    backend_url,
                    "/chat",
                    {
                        "question": question,
                        "length": chat_length,
                        "top_k": chat_top_k,
                        "temperature": chat_temperature,
                        "document_ids": selected_document_ids,
                    },
                )

            if api_error:
                answer = api_error
                st.error(answer)
            else:
                answer = result["answer"]
                st.write(answer)
                if result.get("sources"):
                    st.markdown("**Sources**")
                    for source in result["sources"]:
                        source_line = source["document_title"]
                        if source.get("section_heading"):
                            source_line += f" | {source['section_heading']}"
                        if source.get("source_type"):
                            source_line += f" | {source['source_type']}"
                        if source.get("page"):
                            source_line += f" | page {source['page']}"
                        st.caption(source_line)
                if result.get("processing_notes"):
                    with st.expander("Chat Processing Notes", expanded=False):
                        for note in result["processing_notes"]:
                            st.write(f"- {note}")

        st.session_state.chat_history.append({"role": "assistant", "content": answer})
