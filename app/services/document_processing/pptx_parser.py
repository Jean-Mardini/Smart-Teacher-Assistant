"""PowerPoint (.pptx) specific parsing logic."""

from __future__ import annotations

from pathlib import Path

from app.models.documents import DocumentMetadata, Image, ParsedDocument, Section
from app.services.document_processing.image_assets import save_image_bytes
from app.services.document_processing.image_analysis import analyze_image_bytes


def parse_pptx(path: str | Path) -> ParsedDocument:
    file_path = Path(path)

    try:
        from pptx import Presentation
    except ModuleNotFoundError as exc:
        raise RuntimeError("python-pptx is required to parse PPTX files.") from exc

    presentation = Presentation(file_path)
    sections: list[Section] = []
    images: list[Image] = []

    for slide_index, slide in enumerate(presentation.slides, start=1):
        texts: list[str] = []
        slide_title = f"Slide {slide_index}"
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                clean_text = shape.text.strip()
                if clean_text:
                    texts.append(clean_text)
                    if slide_title == f"Slide {slide_index}":
                        slide_title = clean_text

            if getattr(shape, "shape_type", None) == 13 and hasattr(shape, "image"):
                ocr_text = analyze_image_bytes(shape.image.blob)
                image_number = len(images) + 1
                asset_path = save_image_bytes(
                    file_path,
                    f"slide_{slide_index}_image_{image_number}",
                    shape.image.blob,
                    suffix=f".{getattr(shape.image, 'ext', 'bin')}",
                )
                images.append(
                    Image(
                        image_id=f"slide_{slide_index}_image_{image_number}",
                        page=slide_index,
                        caption=slide_title,
                        description=ocr_text,
                        asset_path=asset_path,
                    )
                )

        if not texts:
            if not any(image.page == slide_index for image in images):
                continue
            title = slide_title
            body_text = ""
        else:
            title = texts[0]
            body_text = "\n".join(texts)

        sections.append(
            Section(
                section_id=f"slide_{slide_index}",
                heading=title,
                level=1,
                page_start=slide_index,
                page_end=slide_index,
                text=body_text,
            )
        )

    return ParsedDocument(
        document_id=file_path.stem.lower().replace(" ", "_"),
        title=file_path.stem,
        metadata=DocumentMetadata(
            filename=file_path.name,
            filetype="pptx",
            source_path=str(file_path),
            total_pages=len(presentation.slides),
        ),
        sections=sections,
        images=images,
    )
