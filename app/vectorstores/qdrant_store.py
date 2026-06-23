from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, List, Optional

import numpy as np

from ..core import config, logging

logger = logging.logger
_CLIENT_CACHE: Dict[str, Any] = {}

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as rest
except Exception:  # pragma: no cover - optional dependency in lean environments
    QdrantClient = None
    rest = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional dependency in lean environments
    SentenceTransformer = None


class QdrantStore:
    def __init__(self):
        self.collection = config.QDRANT_COLLECTION
        self.client = None
        self.embedding_dim = 384
        self.model = None
        self.active_store = "initializing"
        self._json_path = config.QDRANT_LOCAL_PATH / "fallback_vectors.json"
        self._json_store = {"vectors": [], "metadatas": [], "ids": [], "texts": []}

        self._load_embedding_model()
        self._connect_vector_store()

    @property
    def vector_store_name(self) -> str:
        if self.active_store in {"qdrant_local", "json_fallback"}:
            return "local"
        return self.active_store

    @property
    def vector_store_backend(self) -> str:
        return self.active_store

    def _load_embedding_model(self) -> None:
        if SentenceTransformer is None:
            logger.warning("sentence-transformers is unavailable; using deterministic fallback embeddings")
            return
        try:
            self.model = SentenceTransformer(
                config.EMBEDDING_MODEL,
                device=config.EMBEDDING_DEVICE,
                local_files_only=True,
            )
            if hasattr(self.model, "get_embedding_dimension"):
                self.embedding_dim = int(self.model.get_embedding_dimension())
            else:
                self.embedding_dim = int(self.model.get_sentence_embedding_dimension())
        except Exception:
            logger.exception("Failed to load SentenceTransformer model; using deterministic fallback embeddings")
            self.model = None

    def _connect_vector_store(self) -> None:
        requested = (config.VECTOR_STORE or "local").lower()
        if requested == "faiss":
            logger.warning("VECTOR_STORE=faiss requested, but FAISS is not configured; using persistent local fallback")
            requested = "local"

        if requested == "qdrant" and self._try_remote_qdrant():
            return

        if requested == "qdrant":
            logger.warning("Remote Qdrant is unavailable; using persistent local vector store at %s", config.QDRANT_LOCAL_PATH)

        if self._try_local_qdrant():
            return

        logger.warning("Qdrant client local mode is unavailable; using JSON vector fallback at %s", self._json_path)
        self.active_store = "json_fallback"
        self._load_json_store()

    def _try_remote_qdrant(self) -> bool:
        if QdrantClient is None or rest is None or not config.QDRANT_URL:
            return False
        try:
            cache_key = f"remote:{config.QDRANT_URL}:{self.collection}"
            if cache_key in _CLIENT_CACHE:
                self.client = _CLIENT_CACHE[cache_key]
            else:
                self.client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None, timeout=5)
                _CLIENT_CACHE[cache_key] = self.client
            self.client.get_collections()
            self._ensure_collection()
            self.active_store = "qdrant"
            logger.info("Using remote Qdrant vector store at %s, collection=%s", config.QDRANT_URL, self.collection)
            return True
        except Exception as exc:
            logger.warning("Failed to connect to Qdrant at %s: %s", config.QDRANT_URL, exc)
            self.client = None
            return False

    def _try_local_qdrant(self) -> bool:
        if QdrantClient is None or rest is None:
            return False
        try:
            config.QDRANT_LOCAL_PATH.mkdir(parents=True, exist_ok=True)
            cache_key = f"local:{config.QDRANT_LOCAL_PATH}:{self.collection}"
            if cache_key in _CLIENT_CACHE:
                self.client = _CLIENT_CACHE[cache_key]
            else:
                self.client = QdrantClient(path=str(config.QDRANT_LOCAL_PATH), force_disable_check_same_thread=True)
                _CLIENT_CACHE[cache_key] = self.client
            self._ensure_collection()
            self.active_store = "qdrant_local"
            logger.info("Using local Qdrant vector store at %s, collection=%s", config.QDRANT_LOCAL_PATH, self.collection)
            return True
        except Exception as exc:
            logger.warning("Failed to open local Qdrant path %s: %s", config.QDRANT_LOCAL_PATH, exc)
            self.client = None
            return False

    def _collection_exists(self, name: str) -> bool:
        if self.client is None:
            return False
        try:
            return name in [collection.name for collection in self.client.get_collections().collections]
        except Exception:
            return False

    def _ensure_collection(self) -> None:
        if self.client is None or rest is None:
            return
        if config.RESET_VECTOR_STORE and self._collection_exists(self.collection):
            logger.warning("RESET_VECTOR_STORE=true; deleting collection %s", self.collection)
            self.client.delete_collection(collection_name=self.collection)
        if not self._collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=rest.VectorParams(size=self.embedding_dim, distance=rest.Distance.COSINE),
            )
            return

        try:
            info = self.client.get_collection(collection_name=self.collection)
            vectors = info.config.params.vectors
            existing_size = getattr(vectors, "size", None)
            if existing_size and int(existing_size) != self.embedding_dim:
                logger.warning(
                    "Embedding dimension mismatch for collection %s: existing=%s current=%s. "
                    "Run POST /ingest with reset=true before mixing embedding models.",
                    self.collection,
                    existing_size,
                    self.embedding_dim,
                )
        except Exception:
            logger.exception("Could not validate Qdrant collection embedding dimension")

    def _load_json_store(self) -> None:
        if not self._json_path.exists():
            return
        try:
            self._json_store = json.loads(self._json_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read JSON vector fallback; starting with an empty local store")
            self._json_store = {"vectors": [], "metadatas": [], "ids": [], "texts": []}

    def _save_json_store(self) -> None:
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        self._json_path.write_text(json.dumps(self._json_store, indent=2), encoding="utf-8")

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        if self.model is not None:
            embeddings = self.model.encode(
                texts,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=config.NORMALIZE_EMBEDDINGS,
            )
            return [vector.tolist() for vector in embeddings]

        vectors: List[List[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
            vector = [float(digest[index % len(digest)]) / 255.0 for index in range(min(48, self.embedding_dim))]
            vectors.append(vector + [0.0] * max(0, self.embedding_dim - len(vector)))
        return vectors

    def upsert_documents(self, docs: List[Dict[str, Any]]) -> int:
        if not docs:
            return 0

        texts = [doc["text"] for doc in docs]
        ids = [doc["id"] for doc in docs]
        metadatas = [doc["metadata"] for doc in docs]
        vectors = self._embed_texts(texts)

        if self.client is not None:
            from qdrant_client.http.models import PointStruct

            points = []
            for index, doc_id in enumerate(ids):
                payload = {
                    "metadata": metadatas[index],
                    "text": texts[index],
                    "source_file": metadatas[index].get("source_file"),
                    "source_path": metadatas[index].get("source_path"),
                    "page_number": metadatas[index].get("page_number"),
                    "content_type": metadatas[index].get("content_type"),
                    "chunk_type": metadatas[index].get("chunk_type"),
                    "extraction_method": metadatas[index].get("extraction_method"),
                    "file_hash": metadatas[index].get("file_hash"),
                    "file_name": metadatas[index].get("file_name"),
                    "section_title": metadatas[index].get("section_title"),
                    "year": metadatas[index].get("year"),
                    "document_type": metadatas[index].get("document_type"),
                    "quarter": metadatas[index].get("quarter"),
                    "metric_names": metadatas[index].get("metric_names"),
                    "title": metadatas[index].get("title"),
                    "caption": metadatas[index].get("caption"),
                    "figure_number": metadatas[index].get("figure_number"),
                    "visual_type": metadatas[index].get("visual_type"),
                    "contains_chart": metadatas[index].get("contains_chart"),
                    "contains_diagram": metadatas[index].get("contains_diagram"),
                    "contains_table": metadatas[index].get("contains_table"),
                    "contains_image": metadatas[index].get("contains_image"),
                }
                points.append(PointStruct(id=doc_id, vector=vectors[index], payload=payload))
            self.client.upsert(collection_name=self.collection, points=points)
            return len(points)

        for index, doc_id in enumerate(ids):
            if doc_id in self._json_store["ids"]:
                existing_index = self._json_store["ids"].index(doc_id)
                self._json_store["vectors"][existing_index] = vectors[index]
                self._json_store["metadatas"][existing_index] = metadatas[index]
                self._json_store["texts"][existing_index] = texts[index]
            else:
                self._json_store["vectors"].append(vectors[index])
                self._json_store["metadatas"].append(metadatas[index])
                self._json_store["ids"].append(doc_id)
                self._json_store["texts"].append(texts[index])
        self._save_json_store()
        return len(ids)

    def _build_qdrant_filter(self, filter: Optional[Dict[str, Any]]):
        if not filter or rest is None:
            return None
        conditions = []
        for key in ("year", "document_type", "file_name", "page_number", "figure_number"):
            value = filter.get(key)
            if value is None or value == "":
                continue
            conditions.append(rest.FieldCondition(key=key, match=rest.MatchValue(value=value)))
        return rest.Filter(must=conditions) if conditions else None

    def _metadata_matches_filter(self, metadata: Dict[str, Any], filter: Optional[Dict[str, Any]]) -> bool:
        if not filter:
            return True
        for key in ("year", "document_type", "file_name", "page_number", "figure_number"):
            expected = filter.get(key)
            if expected is None or expected == "":
                continue
            actual = metadata.get(key)
            if key == "file_name":
                actual = str(actual or "").lower()
                expected = str(expected).lower()
            if actual != expected:
                return False
        return True

    def search(self, query: str, top_k: int = 5, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        query_vector = self._embed_texts([query])[0]

        if self.client is not None:
            query_filter = self._build_qdrant_filter(filter)
            if hasattr(self.client, "search"):
                hits = self.client.search(
                    collection_name=self.collection,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                )
            else:
                response = self.client.query_points(
                    collection_name=self.collection,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                )
                hits = getattr(response, "points", response)
            results = []
            for hit in hits:
                payload = hit.payload or {}
                metadata = payload.get("metadata", {})
                text = payload.get("text", "")
                results.append({"id": str(hit.id), "score": float(hit.score), "metadata": metadata, "text": text})
            return results

        scores = []
        for index, vector in enumerate(self._json_store["vectors"]):
            metadata = self._json_store["metadatas"][index]
            if not self._metadata_matches_filter(metadata, filter):
                continue
            score = float(np.dot(np.array(query_vector), np.array(vector)))
            scores.append((index, score))

        scores.sort(key=lambda item: item[1], reverse=True)
        results = []
        for index, score in scores[:top_k]:
            results.append(
                {
                    "id": self._json_store["ids"][index],
                    "score": score,
                    "metadata": self._json_store["metadatas"][index],
                    "text": self._json_store["texts"][index],
                }
            )
        return results

    def reconnect(self) -> bool:
        """Retry the configured vector store after a temporary fallback state."""
        self.client = None
        self.active_store = "initializing"
        self._connect_vector_store()
        return self.count_vectors() > 0

    def count_vectors(self) -> int:
        if self.client is not None:
            try:
                result = self.client.count(collection_name=self.collection, exact=True)
                return int(result.count)
            except Exception:
                logger.exception("Failed to count vectors in collection %s", self.collection)
                return 0
        return len(self._json_store["ids"])

    def count_file_vectors(self, file_hash: str) -> int:
        if not file_hash:
            return 0
        if self.client is not None and rest is not None:
            try:
                result = self.client.count(
                    collection_name=self.collection,
                    count_filter=rest.Filter(
                        must=[rest.FieldCondition(key="file_hash", match=rest.MatchValue(value=file_hash))]
                    ),
                    exact=True,
                )
                return int(result.count)
            except Exception:
                logger.exception("Failed to count vectors for file hash %s", file_hash)
                return 0
        return sum(1 for metadata in self._json_store["metadatas"] if metadata.get("file_hash") == file_hash)

    def delete_file_vectors(self, file_hash: str) -> None:
        if not file_hash:
            return
        if self.client is not None and rest is not None:
            try:
                self.client.delete(
                    collection_name=self.collection,
                    points_selector=rest.FilterSelector(
                        filter=rest.Filter(
                            must=[rest.FieldCondition(key="file_hash", match=rest.MatchValue(value=file_hash))]
                        )
                    ),
                )
            except Exception:
                logger.exception("Failed to delete vectors for file hash %s", file_hash)
            return

        keep = [
            index
            for index, metadata in enumerate(self._json_store["metadatas"])
            if metadata.get("file_hash") != file_hash
        ]
        self._json_store = {
            "vectors": [self._json_store["vectors"][index] for index in keep],
            "metadatas": [self._json_store["metadatas"][index] for index in keep],
            "ids": [self._json_store["ids"][index] for index in keep],
            "texts": [self._json_store["texts"][index] for index in keep],
        }
        self._save_json_store()

    def list_chunks(self, file_name: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        if self.client is not None and rest is not None:
            try:
                query_filter = None
                if file_name:
                    query_filter = rest.Filter(
                        must=[rest.FieldCondition(key="file_name", match=rest.MatchValue(value=file_name))]
                    )
                points, _ = self.client.scroll(
                    collection_name=self.collection,
                    scroll_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                    with_vectors=False,
                )
                return [
                    {
                        "id": str(point.id),
                        "metadata": (point.payload or {}).get("metadata", {}),
                        "text": (point.payload or {}).get("text", ""),
                    }
                    for point in points
                ]
            except Exception:
                logger.exception("Failed to list chunks from vector store")
                return []

        chunks = []
        for index, doc_id in enumerate(self._json_store["ids"]):
            metadata = self._json_store["metadatas"][index]
            if file_name and metadata.get("file_name") != file_name:
                continue
            chunks.append({"id": doc_id, "metadata": metadata, "text": self._json_store["texts"][index]})
            if len(chunks) >= limit:
                break
        return chunks

    def clear_collection(self) -> None:
        if self.client is not None:
            try:
                if self._collection_exists(self.collection):
                    self.client.delete_collection(collection_name=self.collection)
                self._ensure_collection()
            except Exception:
                logger.exception("Failed to clear vector store collection")
            return

        self._json_store = {"vectors": [], "metadatas": [], "ids": [], "texts": []}
        if self._json_path.exists():
            self._json_path.unlink()
