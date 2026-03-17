from fastapi import FastAPI
from app.api.routers import agents

app = FastAPI(
    title="Smart Teacher Assistant",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"status": "Smart Teacher Assistant Running 🚀"}

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(agents.router)