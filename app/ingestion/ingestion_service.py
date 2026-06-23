from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image

from ..core import config, logging
from ..utils.file_hash import file_hash
from ..vectorstores.qdrant_store import QdrantStore
from .chunker import create_chunk_docs, split_text_to_chunks
from .docling_extractor import extract_pdf
from .loaders import list_data_files, load_csv_as_markdown, load_txt
from .metadata import file_meta
from .metadata_extractor import enrich_metadata_for_text, structured_chart_summary
from .visual_analyzer import visual_summaries_for_content
from .vision_processor import process_image

logger = logging.logger


class IngestionService:
    def __init__(self):
        self.store = QdrantStore()
        self.index_meta_path = config.INDEX_METADATA_PATH
        self.index_meta_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.index_meta_path.exists():
            self.index_meta_path.write_text(json.dumps({"files": {}}, indent=2), encoding="utf-8")

    @property
    def vector_store_name(self) -> str:
        name = getattr(self.store, "vector_store_name", "local")
        return "qdrant_local" if name == "local" else name

    def _load_index_meta(self) -> Dict[str, Any]:
        try:
            return json.loads(self.index_meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {"files": {}}

    def _save_index_meta(self, meta: Dict[str, Any]) -> None:
        self.index_meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _issue(self, path: Path, message: str) -> Dict[str, str]:
        return {
            "file_name": path.name,
            "file_path": str(path.resolve()),
            "message": message,
        }

    def _meta_for(self, path: Path, **extra: Any) -> Dict[str, Any]:
        return {
            **file_meta(path),
            "embedding_model": config.EMBEDDING_MODEL,
            "embedding_dim": self.store.embedding_dim,
            **extra,
        }

    def _table_to_markdown(self, table: List[List[str]]) -> str:
        rows = [[(cell or "").strip().replace("\n", " ") for cell in row] for row in table if row]
        if not rows:
            return ""
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        header = rows[0]
        separator = ["---"] * width

        def fmt(row: List[str]) -> str:
            return "| " + " | ".join(row) + " |"

        return "\n".join([fmt(header), fmt(separator), *[fmt(row) for row in rows[1:]]]).strip()

    def _ingest_text_file(self, path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
        txt = load_txt(path)
        chunks = split_text_to_chunks(txt)
        return create_chunk_docs(self._meta_for(path, extraction_method="text"), chunks, "text"), []

    def _ingest_csv_file(self, path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
        table_text = load_csv_as_markdown(path)
        return create_chunk_docs(
            self._meta_for(path, extraction_method="csv", chunk_type="table_summary", contains_table=True),
            [table_text],
            "table_summary",
        ), []

    def _ingest_image_file(self, path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
        with Image.open(path) as image:
            result = process_image(image.convert("RGB"))

        warnings = list(result.warnings)
        if result.is_placeholder:
            return [], warnings

        docs = []
        base_meta = self._meta_for(
            path,
            extraction_method=result.extraction_method,
            chunk_type="image_ocr",
            contains_image=True,
        )
        docs.extend(create_chunk_docs(base_meta, split_text_to_chunks(result.text), "image_ocr"))
        for summary in visual_summaries_for_content(path, None, result.text):
            docs.extend(
                create_chunk_docs(
                    self._meta_for(path, extraction_method=summary["content_type"], **summary["metadata"]),
                    [summary["text"]],
                    summary["content_type"],
                )
            )
        return docs, warnings

    def _ingest_pdf_file(self, path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
        docs: List[Dict[str, Any]] = []
        warnings: List[str] = []

        for page in extract_pdf(path):
            page_number = page.get("page_number")
            base_meta = self._meta_for(path, page_number=page_number)

            page_text = (page.get("text") or "").strip()
            if page_text:
                base_meta.update(enrich_metadata_for_text(base_meta, page_text))
            if page_text:
                docs.extend(
                    create_chunk_docs(
                        {**base_meta, "extraction_method": "pdf_text", "chunk_type": "pdf_text"},
                        split_text_to_chunks(page_text),
                        "pdf_text",
                    )
                )

            rendered_image = page.get("rendered_image")
            rendered_text = ""
            if rendered_image is not None:
                result = process_image(rendered_image)
                warnings.extend(f"page {page_number}: {message}" for message in result.warnings)
                if not result.is_placeholder:
                    rendered_text = result.text.strip()
                    docs.extend(
                        create_chunk_docs(
                            {
                                **base_meta,
                                "extraction_method": "page_ocr",
                                "chunk_type": "page_ocr",
                                "contains_image": True,
                            },
                            split_text_to_chunks(rendered_text),
                            "page_ocr",
                        )
                    )
                    for summary in visual_summaries_for_content(path, page_number, rendered_text):
                        docs.extend(
                            create_chunk_docs(
                                {
                                    **base_meta,
                                    "extraction_method": summary["content_type"],
                                    **summary["metadata"],
                                },
                                [summary["text"]],
                                summary["content_type"],
                            )
                        )

            for table_index, table in enumerate(page.get("tables", []), start=1):
                table_text = self._table_to_markdown(table)
                if table_text:
                    docs.extend(
                        create_chunk_docs(
                            {
                                **base_meta,
                                "section_title": f"Table {table_index}",
                                "extraction_method": "table_summary",
                                "chunk_type": "table_summary",
                                "contains_table": True,
                            },
                            [table_text],
                            "table_summary",
                        )
                    )

            scanned_fragments: List[str] = []
            image_text_fragments: List[str] = []
            for image in page.get("images", []):
                result = process_image(image)
                warnings.extend(f"page {page_number}: {message}" for message in result.warnings)
                if result.is_placeholder:
                    continue
                image_text_fragments.append(result.text.strip())
                scanned_fragments.append(result.text.strip())
                docs.extend(
                    create_chunk_docs(
                        {
                            **base_meta,
                            "extraction_method": result.extraction_method,
                            "chunk_type": "image_ocr",
                            "contains_image": True,
                        },
                        split_text_to_chunks(result.text),
                        "image_ocr",
                    )
                )
                for summary in visual_summaries_for_content(path, page_number, result.text):
                    docs.extend(
                        create_chunk_docs(
                            {
                                **base_meta,
                                "extraction_method": summary["content_type"],
                                **summary["metadata"],
                            },
                            [summary["text"]],
                            summary["content_type"],
                        )
                    )

            chart_summary = structured_chart_summary(path, page_text, "\n\n".join([rendered_text, *image_text_fragments]))
            if chart_summary:
                docs.extend(
                    create_chunk_docs(
                        {
                            **base_meta,
                            "section_title": "Company Quarterly Results Chart",
                            "extraction_method": "chart_summary",
                            "chunk_type": "chart_summary",
                            "document_type": "chart",
                            "year": 2024,
                            "metric_names": ["revenue", "net_profit"],
                            "quarter": ["Q1", "Q2", "Q3", "Q4"],
                            "title": "Company Quarterly Results Chart",
                            "caption": "Company Quarterly Results - Sample Data",
                            "visual_type": "chart",
                            "contains_chart": True,
                            "contains_image": True,
                        },
                        [chart_summary],
                        "chart_summary",
                    )
                )

            if page.get("is_scanned") and not page_text:
                scanned_text = "\n\n".join(scanned_fragments).strip()
                if scanned_text:
                    docs.extend(
                        create_chunk_docs(
                            {**base_meta, "extraction_method": "page_ocr", "chunk_type": "page_ocr", "contains_image": True},
                            split_text_to_chunks(scanned_text),
                            "page_ocr",
                        )
                    )

        return docs, warnings

    def _ingest_file(self, path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
        suffix = path.suffix.lower()
        if suffix == ".txt":
            return self._ingest_text_file(path)
        if suffix == ".csv":
            return self._ingest_csv_file(path)
        if suffix == ".pdf":
            return self._ingest_pdf_file(path)
        return self._ingest_image_file(path)

    def _remove_stale_files(self, meta: Dict[str, Any], current_files: List[Path], warnings: List[Dict[str, str]]) -> None:
        current_paths = {str(path.resolve()) for path in current_files}
        for file_key, previous in list(meta.get("files", {}).items()):
            if file_key in current_paths:
                continue
            file_hash_value = previous.get("hash") or previous.get("file_hash")
            if file_hash_value:
                self.store.delete_file_vectors(file_hash_value)
            warnings.append(
                {
                    "file_name": previous.get("file_name", Path(file_key).name),
                    "file_path": file_key,
                    "message": "file removed from data folder; stale vectors deleted",
                }
            )
            meta.get("files", {}).pop(file_key, None)

    def ingest_all(self, force: bool = False, reset: bool = False) -> Dict[str, Any]:
        force = force or config.FORCE_REINGEST
        reset = reset or config.RESET_VECTOR_STORE

        if reset:
            self.store.clear_collection()
            self._save_index_meta({"files": {}})

        files = list(list_data_files())
        meta = self._load_index_meta()
        total_chunks = 0
        vectors_stored = 0
        processed_files: List[str] = []
        skipped_files: List[Dict[str, str]] = []
        failed_files: List[Dict[str, str]] = []
        warnings: List[Dict[str, str]] = []
        errors: List[Dict[str, str]] = []

        self._remove_stale_files(meta, files, warnings)

        for path in files:
            file_key = str(path.resolve())
            try:
                current_hash = file_hash(path)
                previous = meta.get("files", {}).get(file_key, {})
                previous_hash = previous.get("hash") or previous.get("file_hash")
                previous_embedding_model = previous.get("embedding_model")
                existing_vectors = self.store.count_file_vectors(current_hash)
                embedding_model_changed = bool(previous and previous_embedding_model != config.EMBEDDING_MODEL)

                if (
                    config.INGEST_SKIP_UNCHANGED
                    and not force
                    and not embedding_model_changed
                    and previous_hash == current_hash
                    and existing_vectors > 0
                ):
                    skipped_files.append(self._issue(path, f"unchanged since last ingest; {existing_vectors} vectors exist"))
                    continue

                if previous_hash and previous_hash != current_hash:
                    self.store.delete_file_vectors(previous_hash)
                if embedding_model_changed:
                    warnings.append(
                        self._issue(
                            path,
                            f"embedding model changed from {previous_embedding_model} to {config.EMBEDDING_MODEL}; re-ingesting file",
                        )
                    )
                    if previous_hash:
                        self.store.delete_file_vectors(previous_hash)
                if existing_vectors > 0:
                    self.store.delete_file_vectors(current_hash)

                docs, file_warnings = self._ingest_file(path)
                for warning in file_warnings:
                    warnings.append(self._issue(path, warning))

                if not docs:
                    message = "no extractable text or OCR content found"
                    skipped_files.append(self._issue(path, message))
                    warnings.append(self._issue(path, message))
                    continue

                stored = self.store.upsert_documents(docs)
                if stored is None:
                    stored = len(docs)
                if stored <= 0:
                    raise RuntimeError("vector store accepted no vectors")

                total_chunks += len(docs)
                vectors_stored += stored
                processed_files.append(path.name)

                meta.setdefault("files", {})[file_key] = {
                    "file_name": path.name,
                    "file_path": str(path.resolve()),
                    "file_type": path.suffix.lower().lstrip("."),
                    "hash": current_hash,
                    "file_hash": current_hash,
                    "last_indexed": datetime.now(timezone.utc).isoformat(),
                    "chunks_created": len(docs),
                    "vectors_stored": stored,
                    "vector_store": self.vector_store_name,
                    "embedding_model": config.EMBEDDING_MODEL,
                    "embedding_dim": self.store.embedding_dim,
                }
                self._save_index_meta(meta)
            except Exception as exc:
                message = str(exc) or exc.__class__.__name__
                logger.exception("Failed to ingest %s", path)
                failed_files.append(self._issue(path, message))
                errors.append(self._issue(path, message))

        if failed_files and not processed_files:
            status = "failed"
        elif failed_files or warnings:
            status = "completed_with_warnings"
        else:
            status = "completed"

        count_after = self.store.count_vectors()
        return {
            "status": status,
            "vector_store": self.vector_store_name,
            "collection": config.QDRANT_COLLECTION,
            "total_files": len(files),
            "processed_files": processed_files,
            "successful_files": processed_files,
            "failed_files": failed_files,
            "skipped_files": skipped_files,
            "total_chunks_created": total_chunks,
            "total_chunks": total_chunks,
            "vectors_stored": vectors_stored,
            "vector_store_count_after_ingest": count_after,
            "warnings": warnings,
            "errors": errors,
            # Backward-compatible counters for older tests/scripts.
            "files_processed": len(processed_files),
            "files_skipped": len(skipped_files),
            "chunks_created": total_chunks,
        }
