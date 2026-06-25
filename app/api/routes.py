import json
from functools import lru_cache
from typing import List

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response

from ..core import config, logging as logmod
from ..rag.graph import RAGGraph
from ..vectorstores.qdrant_store import QdrantStore
from ..ingestion.ingestion_service import IngestionService
from ..utils.image_visuals import raster_visual_crop_bbox
from ..utils.pdf_visuals import visual_clip_rect
from . import schemas

router = APIRouter()
logger = logmod.logger
IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
}


def _store_with_reconnect() -> QdrantStore:
    store = QdrantStore()
    if store.count_vectors() == 0:
        reconnect = getattr(store, "reconnect", None)
        if callable(reconnect):
            reconnect()
    return store


def _chunk_debug_payload(item: dict, preview_chars: int) -> dict:
    metadata = item.get("metadata", {})
    return {
        "id": item.get("id"),
        "file_name": metadata.get("file_name"),
        "page_number": metadata.get("page_number"),
        "section_title": metadata.get("section_title"),
        "content_type": metadata.get("content_type"),
        "chunk_type": metadata.get("chunk_type"),
        "title": metadata.get("title"),
        "caption": metadata.get("caption"),
        "figure_number": metadata.get("figure_number"),
        "visual_type": metadata.get("visual_type"),
        "contains_chart": metadata.get("contains_chart"),
        "contains_diagram": metadata.get("contains_diagram"),
        "contains_image": metadata.get("contains_image"),
        "year": metadata.get("year"),
        "quarter": metadata.get("quarter"),
        "metric_names": metadata.get("metric_names"),
        "document_type": metadata.get("document_type"),
        "text_preview": (item.get("text") or "")[:preview_chars],
    }


@lru_cache(maxsize=1)
def get_rag_graph() -> RAGGraph:
    return RAGGraph()


@router.get("/health", response_model=schemas.HealthResponse)
def health():
    store = _store_with_reconnect()
    vector_count = store.count_vectors()
    return {
        "status": "ok",
        "vector_store": store.vector_store_name,
        "vector_store_backend": getattr(store, "vector_store_backend", store.vector_store_name),
        "collection": config.QDRANT_COLLECTION,
        "embedding_model": config.EMBEDDING_MODEL,
        "vector_count": vector_count,
    }


@router.post("/ingest", response_model=schemas.IngestResponse)
def ingest(req: schemas.IngestRequest = Body(default_factory=schemas.IngestRequest)):
    try:
        service = IngestionService()
        result = service.ingest_all(force=req.force, reset=req.reset)
        get_rag_graph.cache_clear()
        response = {
            "status": result["status"],
            "vector_store": result["vector_store"],
            "collection": result["collection"],
            "total_files": result["total_files"],
            "processed_files": result["processed_files"],
            "failed_files": result["failed_files"],
            "skipped_files": result["skipped_files"],
            "total_chunks_created": result["total_chunks_created"],
            "vectors_stored": result["vectors_stored"],
            "vector_store_count_after_ingest": result["vector_store_count_after_ingest"],
            "warnings": result["warnings"],
            "errors": result["errors"],
        }
        if result["status"] == "failed":
            return JSONResponse(status_code=500, content=response)
        return response
    except Exception as e:
        logger.exception("Ingest failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=schemas.ChatResponse)
def chat(req: schemas.ChatRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be empty.")
    logger.info("POST /chat received question=%r", question)
    answer, sources = get_rag_graph().run(question)
    if not answer:
        logger.warning("POST /chat produced an empty answer for question=%r", question)
        return {"answer": "I could not find this information in the uploaded documents.", "sources": []}
    return {"answer": answer, "sources": sources}


@router.get("/visuals/{file_name}")
def get_visual(
    file_name: str,
    page_number: int | None = Query(default=None, ge=1),
    crop: str | None = Query(default=None),
):
    safe_name = file_name.replace("\\", "/").split("/")[-1]
    file_path = (config.DATA_DIR / safe_name).resolve()
    data_dir = config.DATA_DIR.resolve()

    if data_dir not in file_path.parents:
        raise HTTPException(status_code=400, detail="Invalid visual path.")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Visual source file was not found.")

    suffix = file_path.suffix.lower()
    if suffix in IMAGE_MEDIA_TYPES:
        if crop == "visual":
            try:
                from PIL import Image

                crop_box = raster_visual_crop_bbox(file_path)
                if crop_box is not None:
                    with Image.open(file_path) as image:
                        cropped = image.convert("RGB").crop(crop_box)
                        import io

                        buffer = io.BytesIO()
                        cropped.save(buffer, format="PNG")
                        return Response(content=buffer.getvalue(), media_type="image/png")
            except Exception as exc:
                logger.exception("Failed to crop visual image file=%s", file_name)
                raise HTTPException(status_code=500, detail="Could not crop the visual source image.") from exc
        return FileResponse(path=file_path, media_type=IMAGE_MEDIA_TYPES[suffix])

    if suffix == ".pdf":
        if page_number is None:
            raise HTTPException(status_code=422, detail="page_number is required for PDF visuals.")
        try:
            import fitz

            with fitz.open(file_path) as document:
                page_index = page_number - 1
                if page_index < 0 or page_index >= document.page_count:
                    raise HTTPException(status_code=404, detail="PDF page was not found.")
                page = document.load_page(page_index)
                clip = None
                if crop == "visual":
                    clip = visual_clip_rect(page)
                    if clip is None:
                        raise HTTPException(status_code=404, detail="No chart or diagram region was found on this page.")
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), clip=clip, alpha=False)
                image_bytes = pixmap.tobytes("png")
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Failed to render visual page file=%s page=%s", file_name, page_number)
            raise HTTPException(status_code=500, detail="Could not render the visual source page.") from exc

        return Response(content=image_bytes, media_type="image/png")

    raise HTTPException(status_code=415, detail="This file type cannot be rendered as a visual.")


@router.post("/debug/search")
def debug_search(req: schemas.DebugSearchRequest):
    ranked = get_rag_graph().debug_search(req.question)
    chunks = []
    for item in ranked:
        payload = _chunk_debug_payload(item, preview_chars=500)
        payload.update(
            {
                "score": item.get("score"),
                "dense_score": item.get("dense_score"),
                "keyword_score": item.get("keyword_score"),
                "metadata_score": item.get("metadata_score"),
                "rerank_score": item.get("rerank_score"),
                "final_score": item.get("final_score"),
            }
        )
        chunks.append(payload)
    return {"question": req.question, "chunks": chunks}


@router.post("/debug/chunks")
def debug_chunks(req: schemas.DebugChunksRequest):
    store = _store_with_reconnect()
    chunks = []
    for item in store.list_chunks(file_name=req.file_name, limit=500):
        payload = _chunk_debug_payload(item, preview_chars=800)
        payload["chunk_index"] = item.get("metadata", {}).get("chunk_index")
        chunks.append(payload)
    return {"file_name": req.file_name, "chunks": chunks, "count": len(chunks)}


@router.get("/documents", response_model=List[schemas.DocumentMeta])
def list_documents():
    path = config.INDEX_METADATA_PATH
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    docs = []
    for _, v in data.get("files", {}).items():
        docs.append({
            "file_name": v.get("file_name"),
            "file_path": v.get("file_path"),
            "file_type": v.get("file_type"),
            "last_indexed": v.get("last_indexed"),
        })
    return docs


@router.delete("/index")
def delete_index():
    # clear Qdrant collection and local metadata
    store = QdrantStore()
    store.clear_collection()
    if config.INDEX_METADATA_PATH.exists():
        config.INDEX_METADATA_PATH.unlink()
    return {"status": "ok"}
