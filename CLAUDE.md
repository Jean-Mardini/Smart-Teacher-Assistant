# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Smart-Teacher-Assistant is a FastAPI backend for an AI-powered teaching tool. It supports document ingestion (PDF/DOCX/PPTX), RAG-based knowledge retrieval, AI agents for grading/summarization/quiz generation, and evaluation services. The project is in early development — the document processing pipeline is functional; most other services are stubs.

## Commands

### Setup
```bash
pip install -r requirements.txt
```

### Run the API server
```bash
uvicorn app.main:app --reload
```

### Run the document processing demo
```bash
python demo_document_processing.py
```
Processes all PDF files in the current directory and saves output as `doc_N.json`.

## Architecture

### Request Flow
`FastAPI routers (app/api/routers/)` → `Service layer (app/services/)` → `Pydantic models (app/models/)`

### Document Processing Pipeline (`app/services/document_processing/`)
The only fully implemented service. Entry point is `process_document(filepath)` exported from `__init__.py`.

Flow: `loaders.py` dispatches to format-specific parsers (`pdf_parser.py`, `docx_parser.py`, `pptx_parser.py`) → `cleaners.py` normalizes text → `structure_extraction.py` splits into sections → `pipeline.py` assembles a `ParsedDocument`.

- PDF parsing uses `fitz` (PyMuPDF) with `pytesseract` OCR fallback for scanned pages.
- Heading detection in `structure_extraction.py` uses 4 heuristics: ALL CAPS, numbered (1.1), Roman numerals, and short title-case lines.
- Output shape: `ParsedDocument` (Pydantic) with `document_id`, `metadata`, `sections[]`, `tables[]`, `full_text`.

### Other Services (stubs)
- `app/services/agents/` — AI agents (chat, grading, quiz, summarizer, etc.) using LangGraph (`orchestration/graph_builder.py`)
- `app/services/knowledge/` — RAG pipeline: chunking, embeddings, ChromaDB vector store, retrieval
- `app/services/evaluation/` — Rubric management, grading, feedback
- `app/services/storage/` — DB and file persistence

### Key Models (`app/models/`)
- `documents.py` — `ParsedDocument`, `Section`, `Table`, `DocumentMetadata` (implemented)
- `agents.py`, `evaluation.py`, `rag.py` — placeholder stubs

### Config
`app/core/config.py` is a placeholder. Environment variables should be loaded via `python-dotenv`.
