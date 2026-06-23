from __future__ import annotations

from typing import Any, Dict, List

from ..core import config, logging
from .query_parser import metadata_priority_score, parse_query_filters

logger = logging.logger

try:
    from sentence_transformers import CrossEncoder
except Exception:  # pragma: no cover - optional dependency in lean environments
    CrossEncoder = None


class Reranker:
    def __init__(self):
        self.model = None
        if not config.USE_RERANKER:
            return
        if CrossEncoder is None:
            logger.warning("CrossEncoder is unavailable; using retrieval scores for reranking")
            return
        try:
            self.model = CrossEncoder(config.RERANKER_MODEL, device=config.EMBEDDING_DEVICE)
            logger.info("Using reranker model %s", config.RERANKER_MODEL)
        except Exception:
            logger.exception("Failed to load reranker model; using retrieval scores")
            self.model = None

    def _answerability_score(self, query: str, candidate: Dict[str, Any]) -> float:
        text = " ".join((candidate.get("text") or "").split()).lower()
        metadata = candidate.get("metadata", {})
        chunk_type = (metadata.get("chunk_type") or metadata.get("content_type") or "").lower()
        content = text.split(" content: ", 1)[-1].strip()
        query_lower = query.lower()
        is_genai_query = any(term in query_lower for term in ("genai", "genal", "generative ai", "generative al"))
        query_filters = parse_query_filters(query)
        score = 0.0

        if len(content) >= 180:
            score += 1.0
        elif len(content) <= 60:
            score -= 1.0

        if chunk_type in {"diagram_summary", "chart_summary"}:
            score += 1.5

        if is_genai_query:
            if "generative artificial intelligence" in text or "generative ai" in text or "generative al" in text:
                score += 4.0
            if "capable of producing novel content" in text:
                score += 3.0
            if "generative ai is inside deep learning" in text:
                score += 3.0
            if chunk_type == "diagram_summary":
                score += 2.5

        if query_filters.get("list_intent"):
            heading = " ".join(
                str(value or "").lower()
                for value in (
                    metadata.get("section_title"),
                    metadata.get("title"),
                    metadata.get("caption"),
                )
            )
            item_hints = (
                "architecture",
                "autoencoder",
                "cnn",
                "convolutional",
                "diffusion",
                "gan",
                "gnn",
                "graph neural",
                "gru",
                "lstm",
                "mamba",
                "model",
                "network",
                "neural network",
                "rnn",
                "recurrent",
                "transformer",
                "vae",
            )
            if any(hint in heading for hint in item_hints):
                score += 4.0
            elif any(hint in content for hint in item_hints):
                score += 2.0
            if "types of " in heading and len(content) < 180:
                score -= 2.0

        return score

    def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        query_filters = parse_query_filters(query)
        limit = max(config.RERANK_TOP_K, 16) if query_filters.get("list_intent") else config.RERANK_TOP_K

        if self.model is None:
            ranked = sorted(
                candidates,
                key=lambda item: float(item.get("score", 0)) + self._answerability_score(query, item),
                reverse=True,
            )
            return ranked[:limit]

        try:
            pairs = [[query, candidate.get("text", "")[:4000]] for candidate in candidates]
            scores = self.model.predict(pairs)
            ranked = []
            for candidate, score in zip(candidates, scores):
                rerank_score = float(score)
                final_score = (
                    float(candidate.get("score") or 0.0)
                    + rerank_score
                    + metadata_priority_score(candidate.get("metadata", {}), query_filters)
                    + self._answerability_score(query, candidate)
                )
                ranked.append({**candidate, "rerank_score": rerank_score, "final_score": final_score})
            ranked.sort(key=lambda item: item.get("final_score", 0), reverse=True)
            top_ranked = ranked[:limit]
            if config.DEBUG_RETRIEVAL_SCORES:
                logger.info("AFTER FILTER/RERANK:")
                for index, item in enumerate(top_ranked, start=1):
                    metadata = item.get("metadata", {})
                    preview = " ".join((item.get("text") or "").split())[:180]
                    logger.info(
                        "%s. %s | year=%s | page=%s | score=%s | rerank=%s | preview=%s",
                        index,
                        metadata.get("file_name"),
                        metadata.get("year"),
                        metadata.get("page_number"),
                        item.get("final_score"),
                        item.get("rerank_score"),
                        preview,
                    )
            return top_ranked
        except Exception:
            logger.exception("Reranker failed; falling back to retrieval scores")
            ranked = sorted(candidates, key=lambda item: item.get("score", 0), reverse=True)
            return ranked[:limit]
