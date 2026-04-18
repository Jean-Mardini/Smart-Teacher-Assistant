"""PDF-specific parsing logic using pdfplumber."""

from __future__ import annotations

from pathlib import Path

from app.models.documents import DocumentMetadata, Image, ParsedDocument, Section
from app.services.document_processing.image_assets import save_rendered_image
from app.services.document_processing.image_analysis import analyze_pil_image


def _extract_pdf_images(page, page_number: int, file_path: Path) -> list[Image]:
    extracted_images: list[Image] = []

    for index, image in enumerate(page.images, start=1):
        caption = f"Embedded image {index} on page {page_number}"
        description = None
        asset_path = None

        try:
            bbox = (
                image.get("x0", 0),
                image.get("top", 0),
                image.get("x1", page.width),
                image.get("bottom", page.height),
            )
            cropped = page.crop(bbox)
            rendered = cropped.to_image(resolution=150)
            description = analyze_pil_image(rendered.original)
            asset_path = save_rendered_image(
                file_path,
                f"pdf_page_{page_number}_image_{index}",
                rendered.original,
            )
        except Exception:
            description = None
            asset_path = None

        extracted_images.append(
            Image(
                image_id=f"pdf_page_{page_number}_image_{index}",
                page=page_number,
                caption=caption,
                description=description,
                asset_path=asset_path,
            )
        )

    return extracted_images


def parse_pdf(path: str | Path) -> ParsedDocument:
    file_path = Path(path)

    try:
        import pdfplumber
    except ModuleNotFoundError as exc:
        raise RuntimeError("pdfplumber is required to parse PDF files.") from exc

    sections: list[Section] = []
    images: list[Image] = []

    with pdfplumber.open(file_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            images.extend(_extract_pdf_images(page, page_number, file_path))
            if not text:
                if not any(image.page == page_number for image in images):
                    continue

            sections.append(
                Section(
                    section_id=f"page_{page_number}",
                    heading=f"Page {page_number}",
                    level=1,
                    page_start=page_number,
                    page_end=page_number,
                    text=text,
                )
            )

        total_pages = len(pdf.pages)

    return ParsedDocument(
        document_id=file_path.stem.lower().replace(" ", "_"),
        title=file_path.stem,
        metadata=DocumentMetadata(
            filename=file_path.name,
            filetype="pdf",
            source_path=str(file_path),
            total_pages=total_pages,
        ),
        sections=sections,
        images=images,
    )
