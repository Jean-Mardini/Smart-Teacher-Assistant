"""FastAPI entrypoint for Smart Teacher Assistant."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import agents, chat, documents, evaluation, rag
from app.storage.files import ensure_storage_dirs

app = FastAPI(
    title="Smart Teacher Assistant",
    version="1.0.0"
)

# Allow local frontend (Vite/React) and Streamlit to call the API during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_storage_dirs()

@app.get("/")
async def root():
    return {"status": "Smart Teacher Assistant Running 🚀"}

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(agents.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(rag.router)
app.include_router(evaluation.router, prefix="/evaluation", tags=["evaluation"])
