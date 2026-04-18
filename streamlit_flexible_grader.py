"""Flexible Grader — Kristy (Streamlit). From repo root: `streamlit run streamlit_flexible_grader.py`."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Tuple

import streamlit as st

from app.services.evaluation import flexible_grader as fg

APP_TITLE = fg.APP_TITLE
UPLOAD_TYPES = fg.UPLOAD_TYPES
append_history = fg.append_history
build_batch_docx_report = fg.build_batch_docx_report
build_batch_report_html = fg.build_batch_report_html
build_docx_report = fg.build_docx_report
build_result_record = fg.build_result_record
build_single_report_html = fg.build_single_report_html
clear_history = fg.clear_history
combine_uploaded_texts = fg.combine_uploaded_texts
export_batch_report = fg.export_batch_report
export_single_report = fg.export_single_report
extract_text = fg.extract_text
generate_items_from_assignment = fg.generate_items_from_assignment
generate_items_from_teacher_key = fg.generate_items_from_teacher_key
grade_submission_fast = fg.grade_submission_fast
load_config = fg.load_config
load_history = fg.load_history
load_presets = fg.load_presets
normalize_points = fg.normalize_points
normalize_uploaded_submissions = fg.normalize_uploaded_submissions
now_iso = fg.now_iso
save_config = fg.save_config
save_presets = fg.save_presets
sanitize_assignment_item = fg.sanitize_assignment_item
sanitize_item_by_origin = fg.sanitize_item_by_origin
sanitize_teacher_key_item = fg.sanitize_teacher_key_item
total_item_points = fg.total_item_points


def has_assignment_text() -> bool:
    return bool((st.session_state.get("assignment_text") or "").strip())


def has_teacher_key() -> bool:
    return bool((st.session_state.get("teacher_key_text") or "").strip())


def has_reference_text() -> bool:
    return bool((st.session_state.get("reference_text") or "").strip())


def get_active_rubric_items() -> List[Dict[str, Any]]:
    return fg.get_active_rubric_items_for_grade(
        str(st.session_state.get("grade_source", "assignment")),
        st.session_state.get("assignment_rubric_items") or [],
        st.session_state.get("teacher_key_rubric_items") or [],
    )


# =========================================================
# UI
# =========================================================
def inject_css() -> None:
    st.markdown(
        """
        <style>
            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(76, 132, 255, 0.08), transparent 26%),
                    radial-gradient(circle at top right, rgba(67, 205, 255, 0.06), transparent 24%),
                    linear-gradient(180deg, #f7f9fc 0%, #eef3f9 100%);
                color: #18212f;
            }

            .block-container {
                padding-top: 1rem;
                padding-bottom: 2rem;
                max-width: 1400px;
            }

            .hero {
                padding: 1.4rem 1.5rem;
                border-radius: 24px;
                background: linear-gradient(135deg, rgba(92, 130, 255, 0.14), rgba(82, 208, 255, 0.10));
                border: 1px solid rgba(87, 111, 145, 0.12);
                box-shadow: 0 18px 40px rgba(26, 45, 79, 0.08);
                margin-bottom: 1rem;
            }

            .hero h1 {
                margin: 0;
                font-size: 2rem;
                color: #152033;
            }

            .hero p {
                margin-top: 0.35rem;
                color: #4c5d78;
                font-size: 1rem;
            }

            .card {
                border: 1px solid rgba(87, 111, 145, 0.10);
                border-radius: 22px;
                padding: 1rem 1rem .9rem 1rem;
                background: rgba(255,255,255,0.88);
                backdrop-filter: blur(8px);
                box-shadow: 0 10px 30px rgba(20, 38, 70, 0.06);
                margin-bottom: 1rem;
            }

            .section-title {
                font-size: 1.08rem;
                font-weight: 700;
                margin-bottom: .25rem;
                color: #18212f;
            }

            .muted {
                color: #66768f;
                font-size: .95rem;
                margin-bottom: .75rem;
            }

            .pill {
                display: inline-block;
                padding: .26rem .62rem;
                border-radius: 999px;
                border: 1px solid rgba(87, 111, 145, 0.12);
                background: #f4f7fb;
                color: #41526b;
                font-size: .8rem;
                margin-right: .35rem;
                margin-bottom: .35rem;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #ffffff 0%, #f6f8fb 100%);
                border-right: 1px solid rgba(87,111,145,0.10);
            }

            div[data-testid="stMetric"] {
                border: 1px solid rgba(87,111,145,0.10);
                border-radius: 18px;
                padding: 0.55rem 0.75rem;
                background: rgba(255,255,255,0.82);
                box-shadow: 0 8px 20px rgba(20, 38, 70, 0.04);
            }

            .stButton > button, .stDownloadButton > button {
                border-radius: 14px !important;
                border: 1px solid rgba(87,111,145,0.10) !important;
                font-weight: 600 !important;
                background: white !important;
                color: #18212f !important;
            }

            .stTextInput input, .stTextArea textarea, .stNumberInput input {
                border-radius: 14px !important;
                background: white !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="hero">
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def start_card(title: str, subtitle: str = "") -> None:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="muted">{subtitle}</div>', unsafe_allow_html=True)


def end_card() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "config": load_config(),

        "assignment_rubric_items": [],
        "assignment_rubric_meta": {},
        "assignment_rubric_ui_ver": 0,

        "teacher_key_rubric_items": [],
        "teacher_key_rubric_meta": {},
        "teacher_key_rubric_ui_ver": 0,

        "rubric_presets": load_presets(),

        "last_result": None,
        "batch_results": [],

        "assignment_text": "",
        "teacher_key_text": "",
        "reference_text": "",

        "menu": "Dashboard",
        "save_history": True,

        "confirm_replace_preset": "",
        "pending_preset_name": "",
        "preview_preset_name": "",
        "loaded_preset_name": "",
        "loaded_preset_origin": "",

        "grade_source": "assignment",
        "preset_source": "assignment",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def render_result(record: Dict[str, Any]) -> None:
    st.metric("Overall score", f"{record.get('overall_score', 0)} / {record.get('overall_out_of', 0)}")
    for item in record.get("items_results", []):
        with st.expander(
            f"{item.get('name', 'Item')} — {item.get('earned_points', 0)} / {item.get('points', 0)}",
            expanded=False,
        ):
            cols = st.columns(4)
            cols[0].caption(f"Origin: {item.get('item_origin', '')}")
            if item.get("mode"):
                cols[1].caption(f"Mode: {item.get('mode', '')}")
            if item.get("grounding"):
                cols[2].caption(f"Grounding: {item.get('grounding', '')}")
            cols[3].caption(f"Points: {item.get('points', 0)}")

            if item.get("description"):
                st.write(item.get("description"))
            if item.get("expected_answer"):
                st.markdown("**Expected answer / guide**")
                st.write(item.get("expected_answer"))
            if item.get("rationale"):
                st.markdown("**Rationale**")
                st.write(item.get("rationale"))
            if item.get("suggestions"):
                st.markdown("**Suggestions**")
                for s in item.get("suggestions", []):
                    st.write("•", s)
            if item.get("evidence"):
                st.markdown("**Evidence**")
                for e in item.get("evidence", [])[:3]:
                    st.write("•", (e.get("quote") or "").strip())


# =========================================================
# Sidebar
# =========================================================
def render_sidebar() -> Tuple[str, int, bool]:
    with st.sidebar:
        st.markdown("## Flexible Grader")
        st.caption("Separated rubrics, light UI, faster grading")

        api_key = st.text_input(
            "Groq API key",
            value=(st.session_state.config.get("GROQ_API_KEY") or ""),
            type="password",
        )
        if st.button("Save API key", use_container_width=True):
            st.session_state.config["GROQ_API_KEY"] = api_key.strip()
            save_config(st.session_state.config)
            st.success("Saved.")
            st.rerun()

        total_points = st.number_input("Overall score out of", min_value=1, max_value=2000, value=100)
        save_history = st.checkbox("Save results to history", value=st.session_state.get("save_history", True))
        st.session_state["save_history"] = save_history

        st.divider()
        menu_items = [
            "Dashboard",
            "Assignment + Rubric",
            "Teacher Key",
            "Reference Files",
            "Presets",
            "Grade",
            "History",
        ]
        selected = st.radio(
            "Menu",
            menu_items,
            index=menu_items.index(st.session_state.get("menu", "Dashboard")),
            label_visibility="collapsed",
        )
        st.session_state["menu"] = selected

        st.divider()
        st.markdown("### Status")
        st.write(f"• Assignment rubric: {len(st.session_state.assignment_rubric_items)}")
        st.write(f"• Teacher-key rubric: {len(st.session_state.teacher_key_rubric_items)}")
        st.write(f"• Assignment text: {'Yes' if has_assignment_text() else 'No'}")
        st.write(f"• Teacher key: {'Yes' if has_teacher_key() else 'No'}")
        st.write(f"• Reference files: {'Yes' if has_reference_text() else 'No'}")
        st.write(f"• Presets: {len(st.session_state.rubric_presets)}")
        st.write(f"• History: {len(load_history(limit=200))}")

    return selected, int(total_points), save_history


# =========================================================
# Shared editor
# =========================================================
def render_rubric_editor(total_points: int, rubric_key: str, ui_ver_key: str) -> None:
    items = st.session_state.get(rubric_key, [])
    if not items:
        return

    start_card("Fine-tune rubric items", "Edit, delete, add, rebalance, then save or grade.")
    ver = st.session_state.get(ui_ver_key, 0)
    edited_items = []
    delete_indices = set()

    for i, item in enumerate(items):
        origin = item.get("item_origin", "assignment")
        with st.expander(f"{i+1}. {item.get('name', 'New Item')}", expanded=(i < 2)):
            c1, c2 = st.columns([2.2, 1.2])

            with c1:
                name = st.text_input("Name", value=item.get("name", ""), key=f"{rubric_key}_name_{ver}_{i}")
                desc = st.text_area("Description", value=item.get("description", ""), height=95, key=f"{rubric_key}_desc_{ver}_{i}")
                exp = ""
                if origin == "teacher_key":
                    exp = st.text_area("Expected answer / guide", value=item.get("expected_answer", ""), height=120, key=f"{rubric_key}_exp_{ver}_{i}")

            with c2:
                pts = st.number_input("Points", min_value=0, max_value=2000, value=int(item.get("points", 0)), key=f"{rubric_key}_pts_{ver}_{i}")

                if origin == "assignment":
                    grounding = st.selectbox(
                        "Grounding",
                        ["ai", "reference", "hybrid"],
                        index=["ai", "reference", "hybrid"].index(item.get("grounding", "ai"))
                        if item.get("grounding", "ai") in ["ai", "reference", "hybrid"] else 0,
                        key=f"{rubric_key}_ground_assign_{ver}_{i}",
                    )
                    mode = ""
                    st.caption("Assignment rubric item")

                else:
                    mode = st.selectbox(
                        "Mode",
                        ["exact", "conceptual"],
                        index=0 if item.get("mode") == "exact" else 1,
                        key=f"{rubric_key}_mode_tk_{ver}_{i}",
                    )
                    if mode == "conceptual":
                        grounding = st.selectbox(
                            "Grounding",
                            ["ai", "reference", "hybrid"],
                            index=["ai", "reference", "hybrid"].index(item.get("grounding", "ai"))
                            if item.get("grounding", "ai") in ["ai", "reference", "hybrid"] else 0,
                            key=f"{rubric_key}_ground_tk_{ver}_{i}",
                        )
                    else:
                        grounding = ""
                        st.caption("No grounding for exact mode")

                delete_me = st.checkbox("Delete this item", value=False, key=f"{rubric_key}_del_{ver}_{i}")

            candidate = sanitize_item_by_origin({
                "item_origin": origin,
                "name": name,
                "description": desc,
                "expected_answer": exp,
                "points": int(pts),
                "mode": mode,
                "grounding": grounding,
            }, origin)

            if delete_me:
                delete_indices.add(i)
            edited_items.append(candidate)

    st.session_state[rubric_key] = [x for idx, x in enumerate(edited_items) if idx not in delete_indices]

    b1, b2, b3 = st.columns(3)

    with b1:
        if st.button("Add item", use_container_width=True, key=f"{rubric_key}_add_btn"):
            origin = items[0].get("item_origin", "assignment") if items else "assignment"
            if origin == "teacher_key":
                st.session_state[rubric_key].append(
                    sanitize_teacher_key_item({
                        "name": "New Item",
                        "description": "",
                        "expected_answer": "",
                        "points": 0,
                        "mode": "conceptual",
                        "grounding": "ai",
                    })
                )
            else:
                st.session_state[rubric_key].append(
                    sanitize_assignment_item({
                        "name": "New Item",
                        "description": "",
                        "points": 0,
                        "grounding": "ai",
                    })
                )
            st.session_state[ui_ver_key] += 1
            st.rerun()

    with b2:
        if st.button("Auto-balance points", use_container_width=True, key=f"{rubric_key}_balance_btn"):
            origin = st.session_state[rubric_key][0].get("item_origin", "assignment") if st.session_state[rubric_key] else "assignment"
            st.session_state[rubric_key] = normalize_points(st.session_state[rubric_key], int(total_points), origin)
            st.session_state[ui_ver_key] += 1
            st.rerun()

    with b3:
        if st.button("Clear all items", use_container_width=True, key=f"{rubric_key}_clear_btn"):
            st.session_state[rubric_key] = []
            st.session_state[ui_ver_key] += 1
            st.rerun()

    current_total = total_item_points(st.session_state[rubric_key])
    if current_total != int(total_points):
        st.error(f"Rubric total is {current_total}. It must equal {int(total_points)}.")
    else:
        st.success(f"Rubric total = {current_total} points.")
    end_card()


# =========================================================
# Pages
# =========================================================
def page_dashboard(total_points: int) -> None:
    hero(APP_TITLE, "Welcome")

    cols = st.columns(6)
    cols[0].metric("A-rubric", len(st.session_state.assignment_rubric_items))
    cols[1].metric("A-total", total_item_points(st.session_state.assignment_rubric_items))
    cols[2].metric("T-rubric", len(st.session_state.teacher_key_rubric_items))
    cols[3].metric("T-total", total_item_points(st.session_state.teacher_key_rubric_items))
    cols[4].metric("Presets", len(st.session_state.rubric_presets))
    cols[5].metric("Reference", "Loaded" if has_reference_text() else "Empty")

    start_card("Workflow", "Organized flow")
    st.markdown('<span class="pill">1. Assignment text → name, description, points, grounding</span>', unsafe_allow_html=True)
    st.markdown('<span class="pill">2. Teacher key → exact / conceptual items</span>', unsafe_allow_html=True)
    st.markdown('<span class="pill">3. Reference files', unsafe_allow_html=True)
    st.markdown('<span class="pill">4. Save/load Presets', unsafe_allow_html=True)
    st.markdown('<span class="pill">5. Grade', unsafe_allow_html=True)
    st.markdown('<span class="pill">6. History', unsafe_allow_html=True)
    end_card()

    if st.session_state.last_result:
        start_card("Most recent result", "")
        render_result(st.session_state.last_result)
        end_card()


def page_assignment_and_rubric(total_points: int) -> None:
    hero("Assignment + Rubric", "Generate assignment-only rubric items.")

    start_card("Generate from assignment", "Produces: name, description, points, grounding.")
    assignment_files = st.file_uploader(
        "Upload assignment files",
        type=UPLOAD_TYPES,
        accept_multiple_files=True,
        key="assignment_files_v9",
    )
    assignment_manual = st.text_area(
        "Or paste assignment text",
        value=st.session_state.get("assignment_text", ""),
        height=240,
        key="assignment_manual_v9",
    )

    assignment_text = combine_uploaded_texts(assignment_files or [], assignment_manual)
    st.session_state.assignment_text = assignment_text

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Generate rubric items", type="primary", use_container_width=True):
            if not (st.session_state.config.get("GROQ_API_KEY") or "").strip():
                st.error("Please save API key first.")
            elif not assignment_text.strip():
                st.error("Please provide assignment text.")
            else:
                with st.spinner("Generating rubric items from assignment..."):
                    result = generate_items_from_assignment(assignment_text, int(total_points))
                items = result.get("items", [])
                if items:
                    st.session_state.assignment_rubric_items = items
                    st.session_state.assignment_rubric_meta = result
                    st.session_state.assignment_rubric_ui_ver += 1
                    st.success("Assignment rubric generated.")
                    st.rerun()
                else:
                    st.error("Could not generate usable rubric items.")

    with c2:
        st.download_button(
            "Download assignment rubric JSON",
            data=json.dumps({"items": st.session_state.assignment_rubric_items}, ensure_ascii=False, indent=2),
            file_name="assignment_rubric_items.json",
            mime="application/json",
            use_container_width=True,
        )
    end_card()

    if st.session_state.assignment_rubric_meta.get("summary"):
        start_card("Generation summary", "")
        for s in st.session_state.assignment_rubric_meta.get("summary", [])[:10]:
            st.write("•", s)
        end_card()

    render_rubric_editor(
        total_points=total_points,
        rubric_key="assignment_rubric_items",
        ui_ver_key="assignment_rubric_ui_ver",
    )


def page_teacher_key(total_points: int) -> None:
    hero("Teacher Key", "Generate teacher-key grading items. Exact for MCQ/T-F, conceptual for QA by default.")

    start_card("Teacher key input", "Produces: name, description, expected answer, points, mode, and grounding only when conceptual.")
    key_files = st.file_uploader(
        "Upload teacher key files",
        type=UPLOAD_TYPES,
        accept_multiple_files=True,
        key="teacher_key_files_page_v9",
    )
    key_manual = st.text_area(
        "Or paste teacher key text",
        value=st.session_state.get("teacher_key_text", ""),
        height=260,
        key="teacher_key_manual_page_v9",
    )

    st.session_state.teacher_key_text = combine_uploaded_texts(key_files or [], key_manual)

    cols = st.columns(2)
    with cols[0]:
        if st.button("Generate rubric items from teacher key", use_container_width=True):
            if not (st.session_state.config.get("GROQ_API_KEY") or "").strip():
                st.error("Please save API key first.")
            elif not st.session_state.teacher_key_text.strip():
                st.error("Please upload or paste a teacher key first.")
            else:
                with st.spinner("Generating rubric items from teacher key..."):
                    result = generate_items_from_teacher_key(st.session_state.teacher_key_text, int(total_points))
                items = result.get("items", [])
                if items:
                    st.session_state.teacher_key_rubric_items = items
                    st.session_state.teacher_key_rubric_meta = result
                    st.session_state.teacher_key_rubric_ui_ver += 1
                    st.success("Teacher-key rubric generated.")
                    st.rerun()
                else:
                    st.error("Could not generate usable rubric items.")
    with cols[1]:
        st.download_button(
            "Download teacher key TXT",
            data=st.session_state.teacher_key_text or "",
            file_name="teacher_key_v9.txt",
            mime="text/plain",
            use_container_width=True,
        )
    end_card()

    if has_teacher_key():
        start_card("Teacher key preview", "")
        st.text_area("Preview", value=st.session_state.teacher_key_text[:3500], height=260, disabled=True)
        end_card()

    render_rubric_editor(
        total_points=total_points,
        rubric_key="teacher_key_rubric_items",
        ui_ver_key="teacher_key_rubric_ui_ver",
    )


def page_reference_files() -> None:
    hero("Reference Files", "Used for assignment grounding and teacher-key conceptual items when needed.")

    start_card("Reference files", "Upload reference material for grounded evaluation.")
    ref_files = st.file_uploader(
        "Upload reference files",
        type=UPLOAD_TYPES,
        accept_multiple_files=True,
        key="reference_files_v9",
    )
    ref_manual = st.text_area(
        "Or paste reference text",
        value=st.session_state.get("reference_text", ""),
        height=260,
        key="reference_manual_v9",
    )

    st.session_state.reference_text = combine_uploaded_texts(ref_files or [], ref_manual)

    st.download_button(
        "Download reference TXT",
        data=st.session_state.reference_text or "",
        file_name="reference_files_v9.txt",
        mime="text/plain",
        use_container_width=True,
    )
    end_card()

    if has_reference_text():
        start_card("Reference preview", "")
        st.text_area("Preview", value=st.session_state.reference_text[:3500], height=260, disabled=True)
        end_card()


def page_presets(total_points: int) -> None:
    hero("Presets", "Save and load assignment or teacher-key rubrics separately, then fine-tune on the same page.")

    st.session_state.preset_source = st.radio(
        "Preset source",
        ["assignment", "teacher_key"],
        horizontal=True,
        key="preset_source_v9"
    )

    current_items = (
        st.session_state.assignment_rubric_items
        if st.session_state.preset_source == "assignment"
        else st.session_state.teacher_key_rubric_items
    )

    start_card("Save current rubric as preset", "Preset = name + rubric items + origin.")
    preset_name = st.text_input(
        "Preset name",
        value=st.session_state.get("pending_preset_name", ""),
        key="preset_name_v9"
    )
    st.session_state.pending_preset_name = preset_name

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save preset", use_container_width=True):
            if not preset_name.strip():
                st.error("Please enter a preset name.")
            elif not current_items:
                st.error("There are no rubric items to save for the selected source.")
            else:
                name = preset_name.strip()
                payload = {
                    "items": current_items,
                    "saved_at": now_iso(),
                    "total_points": total_points,
                    "origin": st.session_state.preset_source,
                }

                if name in st.session_state.rubric_presets:
                    st.session_state["confirm_replace_preset"] = name
                else:
                    st.session_state.rubric_presets[name] = payload
                    save_presets(st.session_state.rubric_presets)
                    st.success(f"Preset '{name}' saved.")
                    st.session_state.pending_preset_name = name

    with c2:
        st.download_button(
            "Download all presets JSON",
            data=json.dumps(st.session_state.rubric_presets, ensure_ascii=False, indent=2),
            file_name="rubric_presets_v9.json",
            mime="application/json",
            use_container_width=True,
        )

    confirm_name = st.session_state.get("confirm_replace_preset", "")
    if confirm_name:
        st.warning(f"Preset '{confirm_name}' already exists. Replace it?")
        a, b = st.columns(2)
        with a:
            if st.button("Yes, replace", use_container_width=True):
                st.session_state.rubric_presets[confirm_name] = {
                    "items": current_items,
                    "saved_at": now_iso(),
                    "total_points": total_points,
                    "origin": st.session_state.preset_source,
                }
                save_presets(st.session_state.rubric_presets)
                st.session_state["confirm_replace_preset"] = ""
                st.session_state.pending_preset_name = confirm_name
                st.success(f"Preset '{confirm_name}' replaced.")
        with b:
            if st.button("Cancel", use_container_width=True):
                st.session_state["confirm_replace_preset"] = ""
    end_card()

    if st.session_state.rubric_presets:
        start_card("Load / preview / delete preset", "Loading keeps it editable below on the same page.")
        names = sorted(list(st.session_state.rubric_presets.keys()))
        selected = st.selectbox("Choose preset", names, key="preset_pick_v9")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("Load preset", use_container_width=True):
                payload = st.session_state.rubric_presets.get(selected, {})
                loaded_items = payload.get("items", [])
                origin = payload.get("origin", "assignment")

                if origin == "teacher_key":
                    st.session_state.teacher_key_rubric_items = [sanitize_item_by_origin(x, "teacher_key") for x in loaded_items]
                    st.session_state.teacher_key_rubric_ui_ver += 1
                else:
                    st.session_state.assignment_rubric_items = [sanitize_item_by_origin(x, "assignment") for x in loaded_items]
                    st.session_state.assignment_rubric_ui_ver += 1

                st.session_state.loaded_preset_name = selected
                st.session_state.loaded_preset_origin = origin
                st.session_state.pending_preset_name = selected
                st.success(f"Loaded preset '{selected}'. Edit it below on this same page.")
        with b2:
            if st.button("Delete preset", use_container_width=True):
                if selected in st.session_state.rubric_presets:
                    del st.session_state.rubric_presets[selected]
                    save_presets(st.session_state.rubric_presets)
                    if st.session_state.get("loaded_preset_name") == selected:
                        st.session_state.loaded_preset_name = ""
                        st.session_state.loaded_preset_origin = ""
                    st.success(f"Deleted preset '{selected}'.")
                    st.rerun()
        with b3:
            if st.button("Preview preset", use_container_width=True):
                st.session_state.preview_preset_name = selected

        preview = st.session_state.get("preview_preset_name", "")
        if preview and preview in st.session_state.rubric_presets:
            payload = st.session_state.rubric_presets[preview]
            rows = []
            for x in payload.get("items", []):
                rows.append({
                    "Origin": x.get("item_origin", payload.get("origin", "")),
                    "Name": x.get("name", ""),
                    "Description": x.get("description", ""),
                    "Expected answer": x.get("expected_answer", ""),
                    "Points": x.get("points", 0),
                    "Mode": x.get("mode", ""),
                    "Grounding": x.get("grounding", ""),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        end_card()

    if st.session_state.loaded_preset_origin == "teacher_key":
        if st.session_state.teacher_key_rubric_items:
            start_card("Loaded preset is now editable", f"You are editing: {st.session_state.loaded_preset_name}")
            st.info("Teacher-key preset loaded. Edit it below, then save over it or under another name.")
            end_card()
            render_rubric_editor(total_points, "teacher_key_rubric_items", "teacher_key_rubric_ui_ver")
    elif st.session_state.loaded_preset_origin == "assignment":
        if st.session_state.assignment_rubric_items:
            start_card("Loaded preset is now editable", f"You are editing: {st.session_state.loaded_preset_name}")
            st.info("Assignment preset loaded. Edit it below, then save over it or under another name.")
            end_card()
            render_rubric_editor(total_points, "assignment_rubric_items", "assignment_rubric_ui_ver")


def page_grade(total_points: int, save_history: bool) -> None:
    hero("Grade", "Choose which rubric source to grade with, then export TXT, DOCX, or printable HTML.")

    grade_source = st.radio(
        "Choose rubric to grade with",
        ["assignment", "teacher_key"],
        horizontal=True,
        key="grade_source_v9"
    )
    st.session_state.grade_source = grade_source

    active_items = get_active_rubric_items()

    if not active_items:
        st.info("Generate or load a rubric first for the selected source.")
        return

    if total_item_points(active_items) != total_points:
        st.warning(
            f"Rubric total is {total_item_points(active_items)} but expected total is {total_points}. "
            "Edit or auto-balance first."
        )
        return

    start_card("Single submission", "Fast scoring + organized report export.")
    submission_file = st.file_uploader("Upload one submission", type=UPLOAD_TYPES, key="single_submission_v9")
    submission_manual = st.text_area("Or paste one submission", height=220, key="single_submission_manual_v9")

    submission_text = ""
    if submission_file is not None:
        submission_text = extract_text(submission_file, submission_file.name)
    if submission_manual.strip():
        submission_text = (submission_text + "\n\n" + submission_manual.strip()).strip()

    if st.button("Grade single submission", type="primary", use_container_width=True):
        if not (st.session_state.config.get("GROQ_API_KEY") or "").strip():
            st.error("Please save API key first.")
        elif not submission_text.strip():
            st.error("Please provide submission text.")
        else:
            with st.spinner("Grading..."):
                result = grade_submission_fast(
                    submission_text=submission_text,
                    items=active_items,
                    teacher_key_text=st.session_state.teacher_key_text,
                    reference_text=st.session_state.reference_text,
                )
            title = getattr(submission_file, "name", None) or "Single Submission"
            record = build_result_record(title, result, submission_text)
            st.session_state.last_result = record
            if save_history:
                append_history(record)

            st.success("Finished.")
            render_result(record)

            single_docx = build_docx_report(record)
            single_html = build_single_report_html(record)

            st.download_button(
                "Download organized single report (TXT)",
                data=export_single_report(record),
                file_name=f"single_report_{record.get('id', 'result')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
            st.download_button(
                "Download single report (DOCX)",
                data=single_docx,
                file_name=f"single_report_{record.get('id', 'result')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
            st.download_button(
                "Download single report (HTML for PDF printing)",
                data=single_html,
                file_name=f"single_report_{record.get('id', 'result')}.html",
                mime="text/html",
                use_container_width=True,
            )
            st.download_button(
                "Download single result JSON",
                data=json.dumps(record, ensure_ascii=False, indent=2),
                file_name=f"single_result_{record.get('id', 'result')}.json",
                mime="application/json",
                use_container_width=True,
            )
    end_card()

    start_card("Batch submissions", "Still fast because each submission uses one grading call.")
    batch_files = st.file_uploader(
        "Upload multiple submissions",
        type=UPLOAD_TYPES,
        accept_multiple_files=True,
        key="batch_files_v9",
    )
    batch_zip = st.file_uploader("Or upload ZIP of submissions", type=["zip"], key="batch_zip_v9")

    if st.button("Grade batch submissions", use_container_width=True):
        if not (st.session_state.config.get("GROQ_API_KEY") or "").strip():
            st.error("Please save API key first.")
        else:
            subs = normalize_uploaded_submissions(batch_files or [], batch_zip)
            if not subs:
                st.error("Please upload multiple files or a ZIP.")
            else:
                records = []
                prog = st.progress(0.0)
                status = st.empty()

                for idx, sub in enumerate(subs, start=1):
                    status.write(f"Grading {idx}/{len(subs)}: {sub['name']}")
                    result = grade_submission_fast(
                        submission_text=sub["text"],
                        items=active_items,
                        teacher_key_text=st.session_state.teacher_key_text,
                        reference_text=st.session_state.reference_text,
                    )
                    rec = build_result_record(sub["name"], result, sub["text"])
                    records.append(rec)
                    if save_history:
                        append_history(rec)
                    prog.progress(idx / len(subs))

                records.sort(key=lambda x: float(x.get("overall_score", 0)), reverse=True)
                st.session_state.batch_results = records
                st.success(f"Finished grading {len(records)} submissions.")
    end_card()

    if st.session_state.batch_results:
        start_card("Batch results", "")
        rows = []
        for i, r in enumerate(st.session_state.batch_results, start=1):
            rows.append({
                "Rank": i,
                "Title": r.get("title", ""),
                "Score": r.get("overall_score", 0),
                "Out of": r.get("overall_out_of", 0),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

        labels = [
            f"#{i} {r.get('title', '(untitled)')} - {r.get('overall_score', 0)}/{r.get('overall_out_of', 0)}"
            for i, r in enumerate(st.session_state.batch_results, start=1)
        ]
        selected = st.selectbox("Open one result", labels, key="open_batch_result_v9")
        idx = labels.index(selected)
        render_result(st.session_state.batch_results[idx])

        batch_docx = build_batch_docx_report(st.session_state.batch_results)
        batch_html = build_batch_report_html(st.session_state.batch_results)

        st.download_button(
            "Download organized batch report (TXT)",
            data=export_batch_report(st.session_state.batch_results),
            file_name=f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True,
        )
        st.download_button(
            "Download batch report (DOCX)",
            data=batch_docx,
            file_name=f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )
        st.download_button(
            "Download batch report (HTML for PDF printing)",
            data=batch_html,
            file_name=f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            mime="text/html",
            use_container_width=True,
        )
        st.download_button(
            "Download batch results JSON",
            data=json.dumps(st.session_state.batch_results, ensure_ascii=False, indent=2),
            file_name=f"batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
        )
        end_card()


def page_history() -> None:
    hero("History", "Reload, inspect, and export past results.")

    hist = load_history(limit=200)
    if not hist:
        st.info("No history yet.")
        return

    start_card("Saved results", "")
    labels = [
        f"{h.get('title', '(untitled)')} — {h.get('overall_score', 0)}/{h.get('overall_out_of', 0)} — {h.get('timestamp', '')}"
        for h in hist
    ]
    selected = st.selectbox("Recent results", labels, key="history_pick_v9")
    idx = labels.index(selected)
    record = hist[idx]

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Load selected result", use_container_width=True):
            st.session_state.last_result = record
            st.success("Loaded.")
            st.rerun()
    with c2:
        if st.button("Clear history", use_container_width=True):
            clear_history()
            st.session_state.last_result = None
            st.success("History cleared.")
            st.rerun()

    render_result(record)

    history_docx = build_docx_report(record)
    history_html = build_single_report_html(record)

    st.download_button(
        "Download organized report (TXT)",
        data=export_single_report(record),
        file_name=f"history_report_{record.get('id', 'record')}.txt",
        mime="text/plain",
        use_container_width=True,
    )
    st.download_button(
        "Download report (DOCX)",
        data=history_docx,
        file_name=f"history_report_{record.get('id', 'record')}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
    st.download_button(
        "Download report (HTML for PDF printing)",
        data=history_html,
        file_name=f"history_report_{record.get('id', 'record')}.html",
        mime="text/html",
        use_container_width=True,
    )
    st.download_button(
        "Download result JSON",
        data=json.dumps(record, ensure_ascii=False, indent=2),
        file_name=f"history_result_{record.get('id', 'record')}.json",
        mime="application/json",
        use_container_width=True,
    )
    end_card()


# =========================================================
# App
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="wide")
inject_css()
init_state()

menu, total_points, save_history = render_sidebar()

if menu == "Dashboard":
    page_dashboard(total_points)
elif menu == "Assignment + Rubric":
    page_assignment_and_rubric(total_points)
elif menu == "Teacher Key":
    page_teacher_key(total_points)
elif menu == "Reference Files":
    page_reference_files()
elif menu == "Presets":
    page_presets(total_points)
elif menu == "Grade":
    page_grade(total_points, save_history)
elif menu == "History":
    page_history()