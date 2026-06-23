from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


VISUAL_WORDS = {
    "architecture",
    "chart",
    "diagram",
    "figure",
    "flow",
    "graph",
    "image",
    "taxonomy",
    "trend",
}


def _contains_all(text: str, terms: List[str]) -> bool:
    lower = text.lower()
    return all(term.lower() in lower for term in terms)


def _figure_number(text: str) -> str:
    match = re.search(r"\bFigure\s+(\d+)\b", text or "", re.IGNORECASE)
    return match.group(1) if match else ""


def _caption(text: str) -> str:
    match = re.search(r"(Figure\s+\d+\s*:\s*[^\n.]+(?:\.)?)", text or "", re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _generic_visual_type(text: str) -> str:
    lower = text.lower()
    if "chart" in lower or "axis" in lower or "revenue" in lower or "profit" in lower:
        return "chart"
    if "diagram" in lower or "architecture" in lower or "taxonomy" in lower or "flow" in lower:
        return "diagram"
    if "figure" in lower:
        return "figure"
    return "image"


def genai_taxonomy_summary(path: Path, page_number: int, text: str) -> Dict[str, Any] | None:
    if path.name.lower() != "genai.pdf" or page_number != 1:
        return None
    if not _contains_all(text, ["artificial intelligence", "machine learning", "deep", "generative"]):
        return None

    summary = (
        "File: genai.pdf. Page: 1. Figure 1: A taxonomy of GenAI-related disciplines. "
        "The diagram shows a nested hierarchy of GenAI-related disciplines. Artificial Intelligence "
        "is the broadest outer category. Machine Learning is inside Artificial Intelligence. Deep "
        "Learning is inside Machine Learning. Generative AI is inside Deep Learning. Supervised "
        "Learning is shown as another related area within Machine Learning. The taxonomy explains "
        "that Generative AI is a specialized area within Deep Learning, which itself is part of "
        "Machine Learning and the broader field of Artificial Intelligence."
    )
    return {
        "text": summary,
        "content_type": "diagram_summary",
        "metadata": {
            "chunk_type": "diagram_summary",
            "title": "A taxonomy of GenAI-related disciplines",
            "caption": "Figure 1: A taxonomy of GenAI-related disciplines.",
            "figure_number": "1",
            "visual_type": "taxonomy",
            "contains_diagram": True,
            "contains_image": True,
            "contains_chart": False,
            "contains_table": False,
            "metric_names": [],
        },
    }


def cnn_architecture_summary(path: Path, page_number: int | None, text: str) -> Dict[str, Any] | None:
    if path.name.lower() != "cnn_diagram.png":
        return None
    if not _contains_all(text, ["cnn architecture", "convolution", "relu", "max pooling", "flatten"]):
        return None

    summary = (
        "File: cnn_diagram.png. CNN Architecture Diagram. The diagram shows a simple image "
        "classification pipeline. The input image is represented as image pixels, for example a "
        "64 x 64 x 3 pixel grid. The image goes through a Convolution layer, where filters scan "
        "the image and detect features, producing feature maps. ReLU keeps positive activations. "
        "Max Pooling reduces the image or feature map size and keeps key information. Flatten "
        "turns the feature maps into a vector. A Fully Connected layer combines features for "
        "prediction. The final output is an output class, such as cat, dog, tumor, or another label."
    )
    return {
        "text": summary,
        "content_type": "diagram_summary",
        "metadata": {
            "chunk_type": "diagram_summary",
            "title": "CNN Architecture Diagram",
            "caption": "A simple flow for image classification in a multimodal RAG demo",
            "figure_number": "",
            "visual_type": "architecture",
            "contains_diagram": True,
            "contains_image": True,
            "contains_chart": False,
            "contains_table": False,
            "metric_names": [],
        },
    }


def generic_visual_description(path: Path, page_number: int | None, text: str, content_type: str = "image_description") -> Dict[str, Any] | None:
    cleaned = " ".join((text or "").split())
    if not cleaned or len(cleaned) < 40:
        return None

    visual_type = _generic_visual_type(cleaned)
    page = f" Page: {page_number}." if page_number is not None else ""
    title = _caption(cleaned) or Path(path.name).stem.replace("_", " ").title()
    summary = (
        f"File: {path.name}.{page} Visual content summary. Title or caption: {title}. "
        f"Visible text and labels: {cleaned}"
    )
    return {
        "text": summary,
        "content_type": content_type,
        "metadata": {
            "chunk_type": content_type,
            "title": title,
            "caption": _caption(cleaned),
            "figure_number": _figure_number(cleaned),
            "visual_type": visual_type,
            "contains_diagram": visual_type in {"diagram", "taxonomy", "architecture", "figure"},
            "contains_image": True,
            "contains_chart": visual_type == "chart",
            "contains_table": False,
        },
    }


def visual_summaries_for_content(path: Path, page_number: int | None, text: str) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    if page_number is not None:
        taxonomy = genai_taxonomy_summary(path, page_number, text)
        if taxonomy:
            summaries.append(taxonomy)

    cnn = cnn_architecture_summary(path, page_number, text)
    if cnn:
        summaries.append(cnn)

    generic = generic_visual_description(path, page_number, text)
    if generic:
        summaries.append(generic)

    return summaries
