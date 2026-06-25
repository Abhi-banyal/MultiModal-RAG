from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency in lean environments
    pytesseract = None


BoxTuple = Tuple[int, int, int, int]

INSTRUCTION_TERMS = {
    "question",
    "questions",
    "prompt",
    "prompts",
    "queries",
    "quiz",
    "exercise",
    "exercises",
}


def _instruction_panel_top(image: Image.Image) -> Optional[int]:
    if pytesseract is None:
        return None

    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except Exception:
        return None

    height = image.height
    candidates = []
    for index, text in enumerate(data.get("text", [])):
        token = str(text or "").strip().lower().strip(":?.!,")
        if token not in INSTRUCTION_TERMS:
            continue
        top = int(data.get("top", [0])[index])
        if top >= int(height * 0.45):
            candidates.append(top)

    if not candidates:
        return None
    return max(0, min(candidates) - 48)


def raster_visual_crop_bbox(path: Path) -> Optional[BoxTuple]:
    """Return a crop box that removes bottom prompt/question panels from demo visuals.

    The crop is intentionally conservative: it only activates when OCR finds
    instruction-like words in the lower half of an image. Normal images without
    such panels are returned unchanged by the caller.
    """

    with Image.open(path) as image:
        top = _instruction_panel_top(image.convert("RGB"))
        if top is None:
            return None
        if top < int(image.height * 0.35):
            return None
        return (0, 0, image.width, top)
