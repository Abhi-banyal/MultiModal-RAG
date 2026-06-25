from __future__ import annotations

import re
from typing import Any, Dict, List

from app.ingestion.metadata_extractor import METRIC_PATTERNS


YEAR_RE = re.compile(r"\b(20\d{2})\b")
QUARTER_RE = re.compile(r"\b(Q[1-4])(?:\s+|\-)?(?:20\d{2})?\b", re.IGNORECASE)
PAGE_RE = re.compile(r"\bpage\s+(\d+)\b", re.IGNORECASE)
FIGURE_RE = re.compile(r"\b(?:figure|fig\.?)\s+(\d+)\b", re.IGNORECASE)
GENAI_RE = re.compile(r"\b(genai|genal|generative\s+ai|generative\s+al|generative\s+artificial\s+intelligence)\b", re.IGNORECASE)

VISUAL_TERMS = {
    "architecture",
    "chart",
    "diagram",
    "figure",
    "flow",
    "graph",
    "image",
    "label",
    "screenshot",
    "taxonomy",
    "trend",
    "visual",
}

CHART_TERMS = {"chart", "graph", "trend", "axis", "legend", "values", "revenue", "profit", "net profit"}
DIAGRAM_TERMS = {"diagram", "taxonomy", "architecture", "flow", "figure"}
LIST_TERMS = {
    "architectures",
    "categories",
    "category",
    "classes",
    "examples",
    "kinds",
    "models",
    "types",
}


def _contains_term(text: str, term: str) -> bool:
    """Return true when a term appears as words, not as a substring."""
    escaped_words = [re.escape(part) for part in term.lower().split()]
    if not escaped_words:
        return False
    pattern = r"\b" + r"\s+".join(escaped_words) + r"s?\b"
    return bool(re.search(pattern, text.lower()))


def parse_query_filters(query: str) -> Dict[str, Any]:
    text = query or ""
    lower = text.lower()

    years = [int(match) for match in YEAR_RE.findall(text)]
    quarters = []
    for match in QUARTER_RE.findall(text):
        quarter = match.upper()
        if quarter not in quarters:
            quarters.append(quarter)

    metrics: List[str] = []
    for name, pattern in METRIC_PATTERNS.items():
        if pattern.search(text):
            metrics.append(name)

    document_type = ""
    for candidate in ("chart", "report", "policy", "diagram"):
        if _contains_term(lower, candidate):
            document_type = candidate
            break

    file_name = ""
    file_match = re.search(r"\b([\w\-]+\.pdf|[\w\-]+\.txt|[\w\-]+\.csv|[\w\-]+\.png|[\w\-]+\.jpe?g)\b", lower)
    if file_match:
        file_name = file_match.group(1)

    page_match = PAGE_RE.search(text)
    figure_match = FIGURE_RE.search(text)
    genai_topic = bool(GENAI_RE.search(text))
    visual = any(_contains_term(lower, term) for term in VISUAL_TERMS)
    chart_intent = any(_contains_term(lower, term) for term in CHART_TERMS)
    diagram_intent = any(_contains_term(lower, term) for term in DIAGRAM_TERMS)
    list_intent = any(_contains_term(lower, term) for term in LIST_TERMS)

    topic_terms = [
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]+", lower)
        if len(token) > 3 and token not in {"what", "does", "from", "show", "explain", "according"}
    ]
    if genai_topic:
        for token in ("generative", "artificial", "intelligence"):
            if token not in topic_terms:
                topic_terms.append(token)

    return {
        "year": years[0] if years else None,
        "years": years,
        "quarter": quarters[0] if len(quarters) == 1 else None,
        "quarters": quarters,
        "metrics": metrics,
        "document_type": document_type or None,
        "file_name": file_name or None,
        "page_number": int(page_match.group(1)) if page_match else None,
        "figure_number": figure_match.group(1) if figure_match else None,
        "genai_topic": genai_topic,
        "visual": visual,
        "chart_intent": chart_intent,
        "diagram_intent": diagram_intent,
        "list_intent": list_intent,
        "topic_terms": topic_terms,
        "needs_year_clarification": bool(metrics and not years),
    }


def metadata_matches_filter(metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    year = filters.get("year")
    if year is not None and metadata.get("year") != year:
        return False

    quarter = filters.get("quarter")
    if quarter:
        metadata_quarter = metadata.get("quarter")
        if isinstance(metadata_quarter, list):
            if quarter not in metadata_quarter:
                return False
        elif metadata_quarter and str(metadata_quarter).upper() != quarter:
            return False

    document_type = filters.get("document_type")
    if document_type and metadata.get("document_type") and metadata.get("document_type") != document_type:
        return False

    file_name = filters.get("file_name")
    if file_name and metadata.get("file_name") and file_name != str(metadata.get("file_name")).lower():
        return False

    page_number = filters.get("page_number")
    if page_number is not None and metadata.get("page_number") not in {None, page_number}:
        return False

    figure_number = filters.get("figure_number")
    if figure_number and metadata.get("figure_number") and str(metadata.get("figure_number")) != str(figure_number):
        return False

    return True


def metadata_priority_score(metadata: Dict[str, Any], filters: Dict[str, Any]) -> float:
    score = 0.0

    year = filters.get("year")
    if year is not None:
        score += 8.0 if metadata.get("year") == year else -25.0

    quarter = filters.get("quarter")
    if quarter:
        metadata_quarter = metadata.get("quarter")
        if isinstance(metadata_quarter, list) and quarter in metadata_quarter:
            score += 4.0
        elif str(metadata_quarter or "").upper() == quarter:
            score += 4.0

    requested_metrics = set(filters.get("metrics") or [])
    if requested_metrics:
        metadata_metrics = set(metadata.get("metric_names") or [])
        score += 2.5 * len(requested_metrics & metadata_metrics)

    document_type = filters.get("document_type")
    if document_type and metadata.get("document_type") == document_type:
        score += 1.5

    file_name = filters.get("file_name")
    if file_name and file_name == str(metadata.get("file_name") or "").lower():
        score += 3.0

    if filters.get("genai_topic") and str(metadata.get("file_name") or "").lower() == "genai.pdf":
        score += 1.5

    page_number = filters.get("page_number")
    if page_number is not None and metadata.get("page_number") == page_number:
        score += 6.0

    figure_number = filters.get("figure_number")
    if figure_number and str(metadata.get("figure_number") or "") == str(figure_number):
        score += 6.0

    chunk_type = metadata.get("chunk_type") or metadata.get("content_type")
    visual_chunks = {"image_description", "chart_summary", "diagram_summary", "image_ocr", "page_ocr"}
    if filters.get("visual") and chunk_type in visual_chunks:
        score += 5.0
    if filters.get("visual") and chunk_type in {"diagram_summary", "chart_summary", "image_description"}:
        score += 4.0
    if filters.get("genai_topic") and chunk_type == "diagram_summary":
        score += 3.0
    if filters.get("chart_intent"):
        score += 8.0 if chunk_type == "chart_summary" else 6.0 if metadata.get("contains_chart") else -1.0
    if filters.get("diagram_intent"):
        score += 8.0 if chunk_type == "diagram_summary" else 6.0 if metadata.get("contains_diagram") else -1.0

    return score
