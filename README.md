# Smart Teacher Assistant

A FastAPI backend for an AI-powered teaching tool. Supports document ingestion (PDF, DOCX, PPTX), structured extraction, and is designed to feed a RAG-based knowledge pipeline for grading, summarization, and quiz generation.

> **Status:** The document processing pipeline is fully implemented. All other services (agents, RAG, evaluation, storage) are stubs in progress.

---

## Setup

**Requirements:** Python 3.10+, and [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed and in PATH (needed for scanned/image-only PDFs).

```bash
pip install -r requirements.txt
```

---

## Running

### API server
```bash
uvicorn app.main:app --reload
```
Health check: `GET /health`

### Document processing demo
```bash
python demo_document_processing.py
```
Drop any `.pdf`, `.docx`, or `.pptx` files into the `samples/` folder, then run the demo. Output JSON files are saved to `outputs/json/` and extracted images to `outputs/images/`.

---

## Project Structure

```
.
├── app/
│   ├── main.py                         # FastAPI app entry point
│   ├── core/
│   │   └── config.py                   # Placeholder — env/settings config goes here
│   ├── api/
│   │   └── routers/
│   │       ├── documents.py            # Document upload/processing endpoints
│   │       ├── agents.py               # AI agent endpoints (stub)
│   │       ├── chat.py                 # Chat endpoint (stub)
│   │       ├── evaluation.py           # Grading/evaluation endpoints (stub)
│   │       └── rag.py                  # RAG retrieval endpoints (stub)
│   ├── models/
│   │   ├── documents.py                # ParsedDocument, Section, Table, Image, DocumentMetadata
│   │   ├── agents.py                   # Agent models (stub)
│   │   ├── evaluation.py               # Evaluation models (stub)
│   │   └── rag.py                      # RAG models (stub)
│   └── services/
│       ├── document_processing/        # Fully implemented
│       │   ├── __init__.py             # Exports process_document(filepath)
│       │   ├── pipeline.py             # Orchestrates the full pipeline
│       │   ├── loaders.py              # Dispatches files to the right parser
│       │   ├── pdf_parser.py           # PDF text + image extraction, OCR fallback, Arabic RTL
│       │   ├── docx_parser.py          # DOCX parsing
│       │   ├── pptx_parser.py          # PPTX slide parsing
│       │   ├── cleaners.py             # Text normalization and cleaning
│       │   ├── structure_extraction.py # Heading detection and section splitting
│       │   └── tables.py               # Table extraction from PDFs
│       ├── agents/                     # AI agents using LangGraph (stub)
│       │   └── orchestration/
│       │       ├── graph_builder.py    # LangGraph agent graph (stub)
│       │       └── state.py            # Agent state definition (stub)
│       ├── knowledge/                  # RAG pipeline — chunking, embeddings, ChromaDB (stub)
│       ├── evaluation/                 # Rubric management, grading, feedback (stub)
│       └── storage/                    # DB and file persistence (stub)
├── demo_document_processing.py         # Runs the pipeline on all files in samples/
├── requirements.txt                    # Python dependencies
├── samples/                            # Put your test documents here (not committed)
└── outputs/
    ├── json/                           # Generated ParsedDocument JSON files
    └── images/                         # Extracted images from documents
```

---

## Document Processing Pipeline

Entry point: `process_document(filepath)` from `app/services/document_processing`.

**Flow:**
1. `loaders.py` — detects file type and dispatches to the right parser
2. `pdf_parser.py` / `docx_parser.py` / `pptx_parser.py` — extracts raw text, tables, and images
3. `cleaners.py` — normalizes whitespace, encoding, and noise
4. `structure_extraction.py` — detects headings and splits content into sections
5. `pipeline.py` — assembles everything into a `ParsedDocument`

**PDF-specific features:**
- Multi-column layout handled via `pdfplumber` fallback
- Arabic RTL text with correct word and character ordering
- OCR fallback via `pytesseract` for scanned/image-only pages
- Image extraction with caption detection

**Output shape (`ParsedDocument`):**
```json
{
  "document_id": "doc_1",
  "title": "...",
  "metadata": {
    "filename": "example.pdf",
    "filetype": "pdf",
    "total_pages": 5,
    "language": "en",
    "ocr_attempted": false,
    "text_extracted": true
  },
  "sections": [{ "section_id": "...", "heading": "...", "level": 1, "text": "..." }],
  "tables": [{ "table_id": "...", "page": 1, "caption": "...", "text": "..." }],
  "images": [{ "image_id": "img_1", "page": 1, "caption": "Figure 1", "path": "..." }],
  "full_text": "..."
}
```

For image-only PDFs where no text can be extracted, `sections` and `tables` will be empty arrays, `images` will still be populated, and `metadata.ocr_attempted` / `metadata.text_extracted` will tell you what happened.

---

## Testing with Your Own Documents

1. Drop a `.pdf`, `.docx`, or `.pptx` file into `samples/`
2. Run `python demo_document_processing.py`
3. Find the output in `outputs/json/doc_N.json`
