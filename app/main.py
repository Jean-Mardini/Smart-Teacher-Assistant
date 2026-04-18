"""FastAPI entrypoint for Smart Teacher Assistant."""

from fastapi import FastAPI

from app.api.routers import agents, chat, documents, evaluation, rag
from app.storage.files import ensure_storage_dirs

app = FastAPI(
    title="Smart Teacher Assistant",
    version="1.0.0"
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
