# Smart Teacher Assistant

USJ capstone — FastAPI backend for document ingestion (PDF, DOCX, PPTX), structured extraction, RAG, LangGraph orchestration, content agents (summaries, slides, quizzes), chat, and evaluation (rubrics + grading).

**Branches:** use **`dev`** for daily work; merge **`dev` → `main`** for submission releases.

---

## Running locally

**Requirements:** Python **3.10+**, **Node.js** (for the Atelier UI). For scanned PDFs, install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) and put it on `PATH`.

### One-time setup (project root)

**Windows (PowerShell)** — from the folder that contains `app/` and `requirements.txt`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env: at minimum set GROQ_API_KEY; optional HF_TOKEN / XAI_API_KEY / OPENAI_API_KEY for slide images
```

**macOS / Linux (bash)** — same folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env (GROQ_API_KEY, etc.)
```

### Terminal A — FastAPI backend

Run from the **repository root** (where `app/main.py` lives), with the venv **activated**:

**Windows**

```powershell
cd C:\path\to\Smart-Teacher-Assistant
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**macOS / Linux**

```bash
cd /path/to/Smart-Teacher-Assistant
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Leave this terminal open. Quick checks:

| URL | Purpose |
|-----|---------|
| http://127.0.0.1:8000/docs | OpenAPI / Swagger |
| http://127.0.0.1:8000/health | Health check |
| http://127.0.0.1:8000/evaluation/status | Evaluation module flags (Kristy) |
| http://127.0.0.1:8000/graph/info | LangGraph orchestration (nodes) |
| http://127.0.0.1:8000/graph/invoke | **Unified teaching workflow** (classify → dialogue / summarize / slides / quiz / grade) |

`POST /chat` runs the same graph with `intent=dialogue` (RAG + Groq). Prefer `POST /graph/invoke` with `intent: auto` to let the model route the request, or set a fixed intent and supply `document_id`, `rubric_items`, etc.

CORS allows local frontends on ports **5173**, **3000**, **8501** (Vite / React / Streamlit). If you use another Vite port, ensure the backend CORS settings include it or use the default ports.

### Terminal B — Atelier (Vite frontend)

```powershell
cd C:\path\to\Smart-Teacher-Assistant\frontend
npm install
npm run dev
```

Open the URL Vite prints (often **http://127.0.0.1:5173**). The UI calls the API at **`VITE_API_URL`** (defaults to `http://127.0.0.1:8000`).

If the backend uses a **different host or port**, create `frontend/.env.local`:

```bash
# copy from example, then edit if needed
cp .env.example .env.local   # macOS / Linux
```

```powershell
Copy-Item .env.example .env.local   # Windows
```

Set `VITE_API_URL` to match Uvicorn (no trailing slash), then **restart** `npm run dev`.

The sidebar has **Library**, **Dialogue**, **Summarize**, **Slides**, **Quiz**, and **Grading**. If you see a connection error, confirm Terminal A is running and `VITE_API_URL` matches the API.

### Optional — Streamlit (second UI)

From the **repository root**, venv activated:

```powershell
streamlit run streamlit_app.py
```

Default Streamlit URL: **http://127.0.0.1:8501** (ensure the Streamlit origin is allowed by CORS if you call the API from it).

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
