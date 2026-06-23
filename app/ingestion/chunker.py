from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

from .metadata_extractor import enrich_metadata_for_text


DEFAULT_CHUNK_SIZE = 3200
DEFAULT_OVERLAP = 450
HEADING_RE = re.compile(r"^([A-Z][A-Za-z0-9 /,&()'\"-]{3,120})$")


def _split_paragraphs(text: str) -> List[str]:
    return [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]


def _split_sentences(text: str) -> List[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def detect_section_title(text: str) -> str:
    for line in text.splitlines()[:12]:
        candidate = line.strip().strip("#").strip()
        if not candidate or len(candidate) > 120:
            continue
        if candidate.endswith(":"):
            return candidate.rstrip(":")
        if HEADING_RE.match(candidate) and len(candidate.split()) <= 12:
            return candidate
    return ""


def _split_long_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    chunks: List[str] = []
    paragraphs = _split_paragraphs(text) or [text.strip()]
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph) <= chunk_size:
            current = paragraph
            continue

        sentence_buffer = ""
        for sentence in _split_sentences(paragraph) or [paragraph]:
            candidate = f"{sentence_buffer} {sentence}".strip() if sentence_buffer else sentence
            if len(candidate) <= chunk_size:
                sentence_buffer = candidate
                continue
            if sentence_buffer:
                chunks.append(sentence_buffer)
                sentence_buffer = sentence
            else:
                start = 0
                while start < len(sentence):
                    end = start + chunk_size
                    chunks.append(sentence[start:end].strip())
                    start = max(end - overlap, end)
                sentence_buffer = ""
        if sentence_buffer:
            current = sentence_buffer

    if current:
        chunks.append(current)

    if overlap <= 0 or len(chunks) <= 1:
        return chunks

    overlapped: List[str] = []
    for index, chunk in enumerate(chunks):
        if index == 0:
            overlapped.append(chunk)
            continue
        prefix = chunks[index - 1][-overlap:].strip()
        overlapped.append(f"{prefix}\n\n{chunk}".strip() if prefix and prefix not in chunk else chunk)
    return overlapped


def split_text_to_chunks(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> List[str]:
    if not text or not text.strip():
        return []

    sections: List[tuple[str, str]] = []
    current_title = ""
    current_lines: List[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        is_heading = bool(stripped and len(stripped) <= 120 and (stripped.endswith(":") or HEADING_RE.match(stripped)))
        if is_heading and current_lines:
            sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = stripped.rstrip(":")
            current_lines = [stripped]
        else:
            if is_heading and not current_title:
                current_title = stripped.rstrip(":")
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))

    chunks: List[str] = []
    for section_title, section_text in sections or [("", text.strip())]:
        for part in _split_long_text(section_text, chunk_size, overlap):
            chunks.append(part)

    deduped: List[str] = []
    seen = set()
    for chunk in chunks:
        normalized = re.sub(r"\s+", " ", chunk).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(chunk.strip())
    return deduped


def _stable_chunk_id(source_meta: Dict[str, Any], index: int, text: str) -> str:
    raw = "|".join(
        [
            str(source_meta.get("file_hash") or ""),
            str(source_meta.get("page_number") or ""),
            str(source_meta.get("content_type") or ""),
            str(index),
            hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12],
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def format_chunk_text(source_meta: Dict[str, Any], text: str) -> str:
    section_title = source_meta.get("section_title") or detect_section_title(text)
    header = [
        f"Document: {source_meta.get('file_name') or source_meta.get('source_file')}",
    ]
    if source_meta.get("page_number") is not None:
        header.append(f"Page: {source_meta.get('page_number')}")
    if section_title:
        header.append(f"Section: {section_title}")
    if source_meta.get("chunk_type"):
        header.append(f"Chunk type: {source_meta.get('chunk_type')}")
    if source_meta.get("title"):
        header.append(f"Title: {source_meta.get('title')}")
    if source_meta.get("caption"):
        header.append(f"Caption: {source_meta.get('caption')}")
    if source_meta.get("figure_number"):
        header.append(f"Figure: {source_meta.get('figure_number')}")
    if source_meta.get("year"):
        header.append(f"Year: {source_meta.get('year')}")
    if source_meta.get("quarter"):
        header.append(f"Quarter: {source_meta.get('quarter')}")
    if source_meta.get("metric_names"):
        header.append(f"Metrics: {', '.join(source_meta.get('metric_names') or [])}")
    header.append("")
    header.append("Content:")
    return "\n".join(header) + f"\n{text.strip()}"


def create_chunk_docs(source_meta: Dict[str, Any], texts: Sequence[str], content_type: str) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    extraction_method = source_meta.get("extraction_method") or content_type
    indexed_at = source_meta.get("indexed_at") or datetime.now(timezone.utc).isoformat()
    base_metadata = {
        "document_id": source_meta.get("document_id") or source_meta.get("file_hash"),
        "file_hash": source_meta.get("file_hash"),
        "source_file": source_meta.get("source_file") or source_meta.get("file_name"),
        "file_name": source_meta.get("file_name"),
        "file_path": source_meta.get("file_path"),
        "source_path": source_meta.get("source_path") or source_meta.get("file_path"),
        "file_type": source_meta.get("file_type"),
        "page_number": source_meta.get("page_number"),
        "section_title": source_meta.get("section_title"),
        "content_type": content_type,
        "chunk_type": source_meta.get("chunk_type") or content_type,
        "extraction_method": extraction_method,
        "year": source_meta.get("year"),
        "document_type": source_meta.get("document_type"),
        "quarter": source_meta.get("quarter"),
        "metric_names": source_meta.get("metric_names") or [],
        "title": source_meta.get("title") or source_meta.get("section_title"),
        "caption": source_meta.get("caption"),
        "figure_number": source_meta.get("figure_number"),
        "visual_type": source_meta.get("visual_type"),
        "contains_chart": bool(source_meta.get("contains_chart")),
        "contains_diagram": bool(source_meta.get("contains_diagram")),
        "contains_table": bool(source_meta.get("contains_table")),
        "contains_image": bool(source_meta.get("contains_image")),
        "indexed_at": indexed_at,
        "created_at": indexed_at,
        "embedding_model": source_meta.get("embedding_model"),
        "embedding_dim": source_meta.get("embedding_dim"),
    }

    seen = set()
    for index, text in enumerate(texts):
        if not text or not str(text).strip():
            continue
        clean_text = str(text).strip()
        normalized = re.sub(r"\s+", " ", clean_text).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        chunk_meta = {**base_metadata, "section_title": base_metadata.get("section_title") or detect_section_title(clean_text)}
        chunk_meta.update(enrich_metadata_for_text(chunk_meta, clean_text))
        chunk_meta["content_type"] = content_type
        chunk_id = _stable_chunk_id({**chunk_meta, "content_type": content_type}, index, clean_text)
        docs.append(
            {
                "id": chunk_id,
                "text": format_chunk_text(chunk_meta, clean_text),
                "metadata": {
                    **chunk_meta,
                    "chunk_id": chunk_id,
                    "chunk_index": index,
                },
            }
        )
    return docs
