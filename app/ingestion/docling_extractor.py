from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional dependency in lean environments
    fitz = None

try:
    import pdfplumber
except Exception:  # pragma: no cover - optional dependency in lean environments
    pdfplumber = None


def _extract_tables_with_pdfplumber(path: Path, page_number: int) -> List[List[List[str]]]:
    if pdfplumber is None:
        return []
    try:
        with pdfplumber.open(path) as pdf:
            if page_number - 1 >= len(pdf.pages):
                return []
            tables = pdf.pages[page_number - 1].extract_tables() or []
            return tables
    except Exception:
        return []


def _extract_images_with_pymupdf(page) -> List[Image.Image]:
    images: List[Image.Image] = []
    try:
        for image_ref in page.get_images(full=True):
            xref = image_ref[0]
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image.get("image")
            if not image_bytes:
                continue
            images.append(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    except Exception:
        return []
    return images


def _render_page_image(page) -> Image.Image | None:
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    except Exception:
        return None


def extract_pdf(path: Path) -> List[Dict[str, Any]]:
    """Extract page-level text, tables, embedded images, and rendered page images from a PDF."""
    if fitz is None:
        raise ImportError("PyMuPDF is required to extract PDF content")

    pages: List[Dict[str, Any]] = []
    with fitz.open(path) as doc:
        for page_index, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            tables = _extract_tables_with_pdfplumber(path, page_index)
            images = _extract_images_with_pymupdf(page)
            rendered_image = _render_page_image(page)
            weak_text = len(text.strip()) < 80
            image_heavy = bool(images) and weak_text
            pages.append(
                {
                    "page_number": page_index,
                    "text": text.strip(),
                    "tables": tables,
                    "images": images,
                    "rendered_image": rendered_image,
                    "is_scanned": image_heavy or (weak_text and rendered_image is not None),
                }
            )
    return pages
