from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

try:
    import fitz
except Exception:  # pragma: no cover - optional dependency in lean environments
    fitz = None


RectTuple = Tuple[float, float, float, float]


def rect_area(rect) -> float:
    return max(0.0, float(rect.width)) * max(0.0, float(rect.height))


def _intersection_area(a, b) -> float:
    x0 = max(float(a.x0), float(b.x0))
    y0 = max(float(a.y0), float(b.y0))
    x1 = min(float(a.x1), float(b.x1))
    y1 = min(float(a.y1), float(b.y1))
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _is_visual_candidate(rect, page_rect) -> bool:
    page_area = rect_area(page_rect)
    candidate_area = rect_area(rect)
    if page_area <= 0 or candidate_area <= 0:
        return False

    area_ratio = candidate_area / page_area
    return area_ratio >= 0.01 and area_ratio <= 0.85 and rect.width >= 40 and rect.height >= 40


def _padded_rect(rect, page_rect, padding: float = 10.0):
    padded = rect + (-padding, -padding, padding, padding)
    return padded & page_rect


def _largest_embedded_image_rect(page):
    image_rects = []
    for image in page.get_images(full=True):
        try:
            image_rects.extend(page.get_image_rects(image[0]))
        except Exception:
            continue

    candidates = [rect for rect in image_rects if _is_visual_candidate(rect, page.rect)]
    if not candidates:
        return None
    return max(candidates, key=rect_area)


def _is_text_heavy(page, rect) -> bool:
    text_chars = 0
    text_lines = 0
    text_area = 0.0
    candidate_area = rect_area(rect)
    if candidate_area <= 0:
        return True

    for block in page.get_text("blocks") or []:
        if len(block) < 5:
            continue
        text = str(block[4] or "").strip()
        if not text:
            continue
        block_rect = fitz.Rect(block[:4])
        overlap = _intersection_area(rect, block_rect)
        if overlap <= 0:
            continue
        if overlap / max(rect_area(block_rect), 1.0) < 0.35:
            continue
        text_chars += len(text)
        text_lines += max(1, text.count("\n") + 1)
        text_area += overlap

    if text_chars > 900 and text_lines > 12:
        return True
    return text_chars > 300 and (text_area / candidate_area) > 0.35


def _drawing_visual_rect(page):
    drawing_rects = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None or not _is_visual_candidate(rect, page.rect):
            continue
        if _is_text_heavy(page, rect):
            continue
        drawing_rects.append(rect)

    if not drawing_rects:
        return None

    union = drawing_rects[0]
    for rect in drawing_rects[1:]:
        union |= rect
    if _is_visual_candidate(union, page.rect) and not _is_text_heavy(page, union):
        return union
    return max(drawing_rects, key=rect_area)


def visual_clip_rect(page):
    rect = _largest_embedded_image_rect(page) or _drawing_visual_rect(page)
    if rect is None:
        return None
    return _padded_rect(rect, page.rect)


def _rect_to_tuple(rect) -> RectTuple:
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


@lru_cache(maxsize=256)
def pdf_visual_clip_bbox(file_path: str, page_number: int) -> Optional[RectTuple]:
    if fitz is None:
        return None

    path = Path(file_path)
    if not path.exists() or not path.is_file() or page_number < 1:
        return None

    try:
        with fitz.open(path) as document:
            page_index = page_number - 1
            if page_index < 0 or page_index >= document.page_count:
                return None
            page = document.load_page(page_index)
            rect = visual_clip_rect(page)
            return _rect_to_tuple(rect) if rect is not None else None
    except Exception:
        return None


def has_pdf_visual_clip(file_path: Path, page_number: int | None) -> bool:
    if page_number is None:
        return False
    return pdf_visual_clip_bbox(str(file_path.resolve()), int(page_number)) is not None
