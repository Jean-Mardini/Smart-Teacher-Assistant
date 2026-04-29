"""FastAPI entrypoint for Smart Teacher Assistant."""

from pathlib import Path

# Load `.env` from the repository root so HF_TOKEN / GROQ_API_KEY work even when
# Uvicorn's working directory is not the project folder (common in IDEs).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv

    # ``override=True`` so values in `.env` win over empty/wrong vars from the shell or OS (common on Windows).
    load_dotenv(_PROJECT_ROOT / ".env", override=True)
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routers import (
    agents,
    chat,
    documents,
    evaluation,
    generate_slides,
    graph,
    rag,
)
from app.services.llm.groq_client import LLMConfigurationError
from app.storage.files import ensure_storage_dirs

app = FastAPI(
    title="Smart Teacher Assistant",
    version="1.0.0"
)

# Allow local frontend (Vite/React) and Streamlit to call the API during development.
# Exact origins cover the common case; regex covers LAN URLs (e.g. http://192.168.x.x:5173),
# which otherwise fail CORS and make the UI show "API offline" while uvicorn is running.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    # Vite may use 5174+ if 5173 is taken; LAN dev uses host + fixed ports.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+|http://[\w.:-]+:(517[3-9]|518\d|3000|8501)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_storage_dirs()


@app.exception_handler(LLMConfigurationError)
async def llm_configuration_handler(_request: Request, exc: LLMConfigurationError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/")
async def root():
    return {"status": "Smart Teacher Assistant Running 🚀"}

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(agents.router)
app.include_router(generate_slides.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(rag.router)
app.include_router(graph.router)
app.include_router(evaluation.router, prefix="/evaluation", tags=["evaluation"])
