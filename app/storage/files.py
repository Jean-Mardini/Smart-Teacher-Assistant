"""File storage utilities: directories for uploads, parsed docs, and results."""

from __future__ import annotations

from pathlib import Path
import re

from app.core.config import settings


def ensure_storage_dirs() -> None:
    for path in (
        settings.data_dir,
        settings.uploads_dir,
        settings.parsed_dir,
        settings.vector_store_path.parent,
        settings.knowledge_base_dir,
        get_evaluation_dir(),
    ):
        Path(path).mkdir(parents=True, exist_ok=True)


def get_knowledge_base_dir() -> Path:
    ensure_storage_dirs()
    return settings.knowledge_base_dir


def get_evaluation_dir() -> Path:
    """Kristy's Flexible Grader: config, presets, and history under data/evaluation/."""
    path = settings.data_dir / "evaluation"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_parsed_images_dir() -> Path:
    ensure_storage_dirs()
    path = settings.parsed_dir / "images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_generated_images_dir() -> Path:
    ensure_storage_dirs()
    path = settings.data_dir / "generated_images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_vector_store_path() -> Path:
    ensure_storage_dirs()
    return settings.vector_store_path


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", filename or "").strip()
    cleaned = cleaned.replace("..", "_")
    return cleaned or "document"
