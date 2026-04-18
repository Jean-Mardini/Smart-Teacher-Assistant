"""Global configuration module."""

"""angelas part"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    data_dir: Path
    uploads_dir: Path
    parsed_dir: Path
    vector_store_path: Path
    knowledge_base_dir: Path
    default_top_k: int = 3
    chunk_size: int = 900
    chunk_overlap: int = 150


def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parents[2]
    data_dir = Path(os.getenv("APP_DATA_DIR", base_dir / "data"))
    knowledge_base_dir = Path(
        os.getenv("KNOWLEDGE_BASE_DIR", data_dir / "knowledge_base")
    )

    return Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        uploads_dir=Path(os.getenv("UPLOADS_DIR", data_dir / "uploads")),
        parsed_dir=Path(os.getenv("PARSED_DIR", data_dir / "parsed")),
        vector_store_path=Path(
            os.getenv("VECTOR_STORE_PATH", data_dir / "vector_store" / "chunks.json")
        ),
        knowledge_base_dir=knowledge_base_dir,
    )


settings = get_settings()
