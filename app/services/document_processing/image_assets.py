"""Helpers for persisting extracted document images as reusable local assets."""

"""angelas part"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

from app.storage.files import get_parsed_images_dir


def _slugify(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "").strip("._-")
    return clean or "document"


def get_document_image_asset_dir(source_path: str | Path) -> Path:
    source = Path(source_path)
    directory = get_parsed_images_dir() / _slugify(source.stem)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_image_bytes(
    source_path: str | Path,
    image_name: str,
    image_bytes: bytes,
    suffix: str | None = None,
) -> str | None:
    if not image_bytes:
        return None

    extension = suffix or ".bin"
    if not extension.startswith("."):
        extension = f".{extension}"

    target = get_document_image_asset_dir(source_path) / f"{_slugify(image_name)}{extension.lower()}"
    target.write_bytes(image_bytes)
    return str(target)


def save_rendered_image(
    source_path: str | Path,
    image_name: str,
    image,
    format_name: str = "PNG",
) -> str | None:
    if image is None:
        return None

    buffer = BytesIO()
    try:
        image.save(buffer, format=format_name)
    except Exception:
        return None

    suffix = f".{format_name.lower()}"
    return save_image_bytes(source_path, image_name, buffer.getvalue(), suffix=suffix)
