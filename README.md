# Smart Teacher Assistant

USJ capstone — FastAPI backend for document ingestion (PDF, DOCX, PPTX), structured extraction, RAG, LangGraph orchestration, content agents (summaries, slides, quizzes), chat, and evaluation (rubrics + grading).

**Branches:** use **`dev`** for daily work; merge **`dev` → `main`** for submission releases.

---

## Setup

**Python 3.10+.** For scanned PDFs, install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) and ensure it is on `PATH`.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # set GROQ_API_KEY and any paths
```

---

## Run API

```bash
python -m uvicorn app.main:app --reload
```

| URL | Purpose |
|-----|---------|
| http://127.0.0.1:8000/docs | OpenAPI / Swagger |
| http://127.0.0.1:8000/health | Health check |
| http://127.0.0.1:8000/evaluation/status | Evaluation module flags (Kristy) |
| http://127.0.0.1:8000/graph/info | LangGraph orchestration (nodes) |
| http://127.0.0.1:8000/graph/invoke | **Unified teaching workflow** (classify → dialogue / summarize / slides / quiz / grade) |

`POST /chat` runs the same graph with `intent=dialogue` (RAG + Groq). Prefer `POST /graph/invoke` with `intent: auto` to let the model route the request, or set a fixed intent and supply `document_id`, `rubric_items`, etc.

CORS allows local frontends on ports 5173, 3000, 8501 (Vite/React/Streamlit).

---

## Document processing (Matheos)

**Entry points:** `process_document(filepath)` or `parse_document(path)` from `app/services/document_processing`.

**Demo (local files in `samples/`):**

```bash
python demo_document_processing.py
```

Outputs JSON under `outputs/json/` and images under `outputs/images/`.

**Pipeline flow:** loaders → pdf/docx/pptx parsers → cleaners → structure extraction + tables → `ParsedDocument` (see Matheos section in repo for PDF/OCR/Arabic details).

---

## Web UI (Vite — recommended)

A dedicated **Atelier** interface lives in `frontend/` (React + TypeScript, not Streamlit).

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually http://127.0.0.1:5173). Run the API on port 8000, or set `VITE_API_URL` in `frontend/.env.local` (see `frontend/.env.example`).

The sidebar separates **Library**, **Dialogue**, **Summarize**, **Slides**, **Quiz**, and **Grading** — each screen can upload or pick a document where needed. If the UI shows a connection error, ensure uvicorn is running and `VITE_API_URL` matches it.

## Optional UIs (Streamlit)

```bash
streamlit run streamlit_app.py
```

---

## Layout

| Area | Path |
|------|------|
| Web UI (Atelier) | `frontend/` |
| API routers | `app/api/routers/` |
| Models | `app/models/` |
| Document processing | `app/services/document_processing/` |
| RAG / knowledge | `app/services/knowledge/` |
| Agents | `app/services/agents/` |
| LangGraph orchestration | `app/services/agents/orchestration/` (`assistant_graph.py`) |
| Evaluation | `app/services/evaluation/` |
| Orchestration (optional) | `app/services/agents/orchestration/` |

---

## Team integration order

Matheos (documents) → Mark (RAG) → Kristy (evaluation, can be merged manually) → Mike (frontend).
