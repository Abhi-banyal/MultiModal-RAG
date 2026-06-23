from PIL import Image

from ..core import config, logging

logger = logging.logger

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency in lean environments
    pytesseract = None

if pytesseract is not None and config.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD


def ocr_image(path_or_image) -> str:
    """Run OCR with Tesseract when available. Accepts Path or PIL Image."""
    if pytesseract is None:
        return ""

    if hasattr(path_or_image, "mode") and hasattr(path_or_image, "size"):
        image = path_or_image
    else:
        image = Image.open(path_or_image)
    try:
        text = pytesseract.image_to_string(image)
    except Exception as exc:
        # Tesseract is an external binary. If it is missing or misconfigured,
        # let ingestion continue with the rest of the extracted content.
        logger.warning("Tesseract OCR failed: %s", exc)
        return ""
    return text or ""
