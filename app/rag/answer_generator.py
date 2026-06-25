from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from ..core import config, logging
from ..ingestion.metadata_extractor import extract_year
from ..utils.pdf_visuals import has_pdf_visual_clip
from .query_parser import parse_query_filters
from .prompts import build_prompt

logger = logging.logger

VISUAL_CHUNK_TYPES = {
    "chart_summary",
    "diagram_summary",
    "image_description",
    "image_ocr",
    "page_ocr",
}
PDF_VISUAL_CHUNK_TYPES = {"chart_summary", "diagram_summary"}
PDF_VISUAL_TYPES = {"chart", "diagram", "taxonomy", "architecture", "figure", "flowchart"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

try:
    from openai import AzureOpenAI
except Exception:  # pragma: no cover - optional dependency in lean environments
    AzureOpenAI = None


class AnswerGenerator:
    def __init__(self):
        self.client = None
        self.model = ""
        self.provider = "extractive"

        if config.USE_AZURE_OPENAI:
            self._configure_azure_openai()

    def _configure_azure_openai(self) -> None:
        required = [
            config.AZURE_OPENAI_ENDPOINT,
            config.AZURE_OPENAI_API_KEY,
            config.AZURE_OPENAI_API_VERSION,
            config.AZURE_OPENAI_DEPLOYMENT,
        ]
        if not all(required):
            logger.error("Azure OpenAI is enabled but AZURE_OPENAI_ENDPOINT/API_KEY/API_VERSION/DEPLOYMENT is missing.")
            return
        if AzureOpenAI is None:
            logger.error("Azure OpenAI is enabled but the openai package is not available.")
            return

        self.client = AzureOpenAI(
            api_key=config.AZURE_OPENAI_API_KEY,
            api_version=config.AZURE_OPENAI_API_VERSION,
            azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
        )
        self.model = config.AZURE_OPENAI_DEPLOYMENT
        self.provider = "azure"
        logger.info("Using Azure OpenAI for answer generation with deployment=%s", self.model)

    def _extractive_answer(self, context_chunks: List[Dict[str, Any]], with_prefix: bool = False) -> str:
        texts = [chunk.get("text", "").strip() for chunk in context_chunks if chunk.get("text")]
        if not texts:
            return ""
        excerpt = "\n\n".join(texts[:4])[:3000]
        if not with_prefix:
            return excerpt
        return (
            "I found relevant information in the uploaded documents, but the AI answer generation service "
            f"is unavailable. Based on the retrieved context: {excerpt}"
        )

    def _visual_url(self, metadata: Dict[str, Any], include_pdf_visuals: bool = True) -> Optional[str]:
        file_name = metadata.get("file_name")
        if not file_name:
            return None

        suffix = Path(file_name).suffix.lower()
        chunk_type = metadata.get("chunk_type") or metadata.get("content_type")

        if suffix in IMAGE_EXTENSIONS:
            if (
                chunk_type in VISUAL_CHUNK_TYPES
                or metadata.get("contains_chart")
                or metadata.get("contains_diagram")
                or metadata.get("contains_image")
            ):
                return f"/visuals/{quote(file_name)}?crop=visual"
            return f"/visuals/{quote(file_name)}"

        if suffix != ".pdf" or metadata.get("page_number") is None:
            return None
        if not include_pdf_visuals and chunk_type not in PDF_VISUAL_CHUNK_TYPES:
            return None

        visual_type = str(metadata.get("visual_type") or "").lower()
        has_chart_or_diagram_metadata = bool(
            chunk_type in PDF_VISUAL_CHUNK_TYPES
            or metadata.get("contains_chart")
            or metadata.get("contains_diagram")
            or visual_type in PDF_VISUAL_TYPES
            or metadata.get("figure_number")
        )
        is_generic_page_image = chunk_type in {"image_description", "image_ocr", "page_ocr"} and visual_type in {"", "image"}
        if not has_chart_or_diagram_metadata or is_generic_page_image:
            return None

        file_path = (config.DATA_DIR / str(file_name)).resolve()
        if has_pdf_visual_clip(file_path, metadata.get("page_number")):
            return f"/visuals/{quote(file_name)}?page_number={metadata.get('page_number')}&crop=visual"

        return None

    def _chunk_score(self, chunk: Dict[str, Any]) -> float:
        for key in ("final_score", "score", "rerank_score"):
            try:
                value = float(chunk.get(key) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value:
                return value
        return 0.0

    def _source_key(self, chunk: Dict[str, Any]) -> Tuple[Any, Any, Any]:
        metadata = chunk.get("metadata", {})
        return (
            metadata.get("file_name"),
            metadata.get("page_number"),
            metadata.get("content_type"),
        )

    def _visual_scope_key(self, chunk: Dict[str, Any]) -> Tuple[Any, Any, Any]:
        metadata = chunk.get("metadata", {})
        figure_number = metadata.get("figure_number") or None
        page_number = metadata.get("page_number")
        return (
            metadata.get("file_name"),
            page_number,
            figure_number if figure_number is not None else page_number,
        )

    def _select_evidence_chunks(
        self,
        question: str,
        query_filters: Dict[str, Any],
        context_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not query_filters.get("visual"):
            non_generic_chunks = [
                chunk for chunk in context_chunks if not self._is_generic_pdf_page_image(chunk.get("metadata", {}))
            ]
            if non_generic_chunks:
                context_chunks = non_generic_chunks
            non_page_image_chunks = [
                chunk
                for chunk in context_chunks
                if not self._is_pdf_image_description(chunk.get("metadata", {}))
            ]
            if non_page_image_chunks:
                context_chunks = non_page_image_chunks

        if len(context_chunks) <= 1:
            return context_chunks

        if query_filters.get("visual") and not query_filters.get("list_intent"):
            top_chunk = context_chunks[0]
            top_scope = self._visual_scope_key(top_chunk)
            scoped_chunks = [
                chunk
                for chunk in context_chunks
                if self._visual_scope_key(chunk) == top_scope
                or (
                    chunk.get("metadata", {}).get("file_name") == top_scope[0]
                    and top_scope[1] is None
                    and top_scope[2] is None
                )
            ]
            if scoped_chunks:
                return scoped_chunks

        top_chunk = context_chunks[0]
        top_score = self._chunk_score(top_chunk)
        if top_score <= 0:
            return context_chunks

        top_key = self._source_key(top_chunk)
        threshold = top_score * 0.45
        selected = [
            chunk
            for index, chunk in enumerate(context_chunks)
            if index == 0 or self._source_key(chunk) == top_key or self._chunk_score(chunk) >= threshold
        ]
        return selected or [top_chunk]

    def _is_generic_pdf_page_image(self, metadata: Dict[str, Any]) -> bool:
        file_name = metadata.get("file_name") or ""
        if Path(str(file_name)).suffix.lower() != ".pdf":
            return False
        chunk_type = metadata.get("chunk_type") or metadata.get("content_type")
        visual_type = str(metadata.get("visual_type") or "").lower()
        return bool(
            chunk_type == "image_description"
            and visual_type in {"", "image"}
            and not metadata.get("contains_chart")
            and not metadata.get("contains_diagram")
        )

    def _is_pdf_image_description(self, metadata: Dict[str, Any]) -> bool:
        file_name = metadata.get("file_name") or ""
        if Path(str(file_name)).suffix.lower() != ".pdf":
            return False
        chunk_type = metadata.get("chunk_type") or metadata.get("content_type")
        return chunk_type == "image_description"

    def _build_sources(self, context_chunks: List[Dict[str, Any]], include_pdf_visuals: bool = True) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        seen = set()
        for chunk in context_chunks:
            md = chunk.get("metadata", {})
            source = (
                md.get("file_name"),
                md.get("page_number"),
                md.get("content_type"),
            )
            if source in seen:
                continue
            seen.add(source)
            visual_url = self._visual_url(md, include_pdf_visuals=include_pdf_visuals)
            chunk_type = md.get("chunk_type") or md.get("content_type")
            visual_type = md.get("visual_type") if visual_url or chunk_type in VISUAL_CHUNK_TYPES else None
            sources.append(
                {
                    "file_name": md.get("file_name"),
                    "page_number": md.get("page_number"),
                    "content_type": md.get("content_type"),
                    "chunk_type": md.get("chunk_type"),
                    "title": md.get("title"),
                    "caption": md.get("caption"),
                    "figure_number": md.get("figure_number"),
                    "visual_type": visual_type,
                    "year": md.get("year"),
                    "quarter": md.get("quarter"),
                    "score": chunk.get("score"),
                    "rerank_score": chunk.get("rerank_score"),
                    "matched_text_preview": " ".join((chunk.get("text") or "").split())[:300],
                    "visual_url": visual_url,
                    "visual_label": md.get("caption") or md.get("title") or md.get("file_name"),
                }
            )
        return sources

    def _call_answer_model(self, prompt: str) -> Optional[str]:
        if self.client is None or not self.model:
            return None

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You answer questions using only retrieved document context. "
                        "Be direct, concise, and do not invent facts."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        return (response.choices[0].message.content or "").strip()

    def generate(self, question: str, context_chunks: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
        if not context_chunks:
            return ("", [])

        query_filters = parse_query_filters(question)
        requested_year = query_filters.get("year")
        if requested_year is not None:
            matching_chunks = []
            for chunk in context_chunks:
                metadata = chunk.get("metadata", {})
                chunk_year = metadata.get("year") or extract_year(chunk.get("text", ""))
                if chunk_year == requested_year:
                    if metadata.get("year") is None:
                        chunk = {**chunk, "metadata": {**metadata, "year": requested_year}}
                    matching_chunks.append(chunk)
            context_chunks = matching_chunks
            if not context_chunks:
                return (f"I could not find this information in the uploaded documents for {requested_year}.", [])

        context_chunks = self._select_evidence_chunks(question, query_filters, context_chunks)
        include_pdf_visuals = bool(
            query_filters.get("visual")
            or query_filters.get("chart_intent")
            or query_filters.get("diagram_intent")
            or any(
                (chunk.get("metadata", {}).get("chunk_type") or chunk.get("metadata", {}).get("content_type"))
                in PDF_VISUAL_CHUNK_TYPES
                for chunk in context_chunks
            )
        )
        sources = self._build_sources(context_chunks, include_pdf_visuals=include_pdf_visuals)
        prompt = build_prompt(context_chunks, question)

        if self.client is None:
            return (self._extractive_answer(context_chunks, with_prefix=True), sources)

        try:
            answer = self._call_answer_model(prompt)
        except Exception as exc:
            if self.provider == "azure":
                logger.exception("Azure OpenAI deployment failed. Check AZURE_OPENAI_DEPLOYMENT in .env. Details: %s", exc)
            else:
                logger.exception("Answer generation failed; falling back to extractive mode. Details: %s", exc)
            answer = None

        if not answer:
            answer = self._extractive_answer(context_chunks, with_prefix=True)
        return (answer, sources)
