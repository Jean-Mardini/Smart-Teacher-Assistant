"""Word (.docx) specific parsing logic."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from app.models.documents import DocumentMetadata, Image, ParsedDocument, Section
from app.services.document_processing.image_assets import save_image_bytes
from app.services.document_processing.image_analysis import analyze_image_bytes


def parse_docx(path: str | Path) -> ParsedDocument:
    file_path = Path(path)

    try:
        from docx import Document
    except ModuleNotFoundError as exc:
        raise RuntimeError("python-docx is required to parse DOCX files.") from exc

    document = Document(file_path)
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    full_text = "\n\n".join(paragraphs)
    images: list[Image] = []

    try:
        with ZipFile(file_path) as archive:
            media_files = sorted(
                name for name in archive.namelist()
                if name.startswith("word/media/")
            )
            for index, media_name in enumerate(media_files, start=1):
                image_bytes = archive.read(media_name)
                ocr_text = analyze_image_bytes(image_bytes)
                asset_path = save_image_bytes(
                    file_path,
                    f"docx_image_{index}",
                    image_bytes,
                    suffix=Path(media_name).suffix or ".bin",
                )
                images.append(
                    Image(
                        image_id=f"docx_image_{index}",
                        page=1,
                        caption=f"Embedded image {index}",
                        description=ocr_text,
                        asset_path=asset_path,
                    )
                )
    except Exception:
        images = []

    return ParsedDocument(
        document_id=file_path.stem.lower().replace(" ", "_"),
        title=file_path.stem,
        metadata=DocumentMetadata(
            filename=file_path.name,
            filetype="docx",
            source_path=str(file_path),
            total_pages=1,
        ),
        sections=[
            Section(
                section_id="section_1",
                heading="Document",
                level=1,
                page_start=1,
                page_end=1,
                text=full_text,
            )
        ],
        images=images,
    )
