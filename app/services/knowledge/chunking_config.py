"""Runtime chunking configuration."""

from __future__ import annotations

import json

from app.core.config import settings
from app.models.rag import ChunkingConfig


def _config_path():
    return settings.data_dir / "rag_chunking_config.json"


def get_chunking_config() -> ChunkingConfig:
    path = _config_path()
    if not path.exists():
        return ChunkingConfig(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ChunkingConfig(**payload)
    except Exception:
        return ChunkingConfig(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )


def save_chunking_config(chunk_size: int, chunk_overlap: int) -> ChunkingConfig:
    config = ChunkingConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    return config
