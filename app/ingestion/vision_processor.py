from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import List, Optional

from PIL import Image

from ..core import config, logging
from .image_ocr import ocr_image

logger = logging.logger

try:
    from openai import AzureOpenAI
except Exception:  # pragma: no cover - optional dependency in lean environments
    AzureOpenAI = None


@dataclass
class VisionProcessingResult:
    text: str
    extraction_method: str
    warnings: List[str] = field(default_factory=list)
    is_placeholder: bool = False


def _azure_openai_client() -> Optional["AzureOpenAI"]:
    if AzureOpenAI is None:
        return None
    required = [
        config.AZURE_OPENAI_ENDPOINT,
        config.AZURE_OPENAI_API_KEY,
        config.AZURE_OPENAI_API_VERSION,
        config.AZURE_OPENAI_DEPLOYMENT,
    ]
    if not all(required):
        return None
    return AzureOpenAI(
        api_key=config.AZURE_OPENAI_API_KEY,
        api_version=config.AZURE_OPENAI_API_VERSION,
        azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
    )


def _describe_with_vision_model(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    prompt = (
        "Describe this visual content for multimodal RAG. Extract every visible title, caption, "
        "label, legend, axis, value, unit, relationship, hierarchy, flow, and important observation. "
        "For taxonomy or architecture diagrams, explain nesting and relationships. For charts, list "
        "series, quarters/categories, exact values, units, and trends. Be structured and factual."
    )

    azure_client = _azure_openai_client()
    if azure_client is not None:
        response = azure_client.chat.completions.create(
            model=config.AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                    ],
                }
            ],
            temperature=0.0,
        )
        return (response.choices[0].message.content or "").strip()

    return ""


def process_image(image: Image.Image) -> VisionProcessingResult:
    """Extract image text safely.

    Tesseract OCR is always attempted first. OpenAI vision is optional enrichment
    and any provider failure becomes a warning instead of an ingestion failure.
    """

    warnings: List[str] = []
    ocr_text = (ocr_image(image) or "").strip()
    if ocr_text:
        base_text = f"OCR extracted text:\n{ocr_text}"
        extraction_method = "image_ocr"
    else:
        base_text = ""
        extraction_method = "vision_fallback"
        warnings.append("Image processed, but no readable OCR text found.")

    if not config.USE_OPENAI_VISION:
        if base_text:
            return VisionProcessingResult(base_text, extraction_method, warnings)
        return VisionProcessingResult(
            "Image processed, but no readable OCR text found.",
            "vision_fallback",
            warnings,
            is_placeholder=True,
        )

    try:
        vision_text = _describe_with_vision_model(image)
    except Exception as exc:
        message = f"OpenAI vision failed; continued with OCR fallback: {exc}"
        logger.warning(message)
        warnings.append(message)
        vision_text = ""

    if vision_text and ocr_text:
        return VisionProcessingResult(
            f"{base_text}\n\nVision description:\n{vision_text}",
            "image_ocr",
            warnings,
        )
    if vision_text:
        return VisionProcessingResult(vision_text, "vision_fallback", warnings)
    if base_text:
        return VisionProcessingResult(base_text, extraction_method, warnings)

    return VisionProcessingResult(
        "Image processed, but no readable OCR text found.",
        "vision_fallback",
        warnings,
        is_placeholder=True,
    )


def describe_image(image: Image.Image) -> str:
    """Backward-compatible string helper used by older callers/tests."""

    return process_image(image).text
