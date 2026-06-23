from __future__ import annotations

import re
from typing import Any, Dict, List

from ..core import config, logging
from ..vectorstores.qdrant_store import QdrantStore
from .query_parser import metadata_matches_filter, metadata_priority_score, parse_query_filters

logger = logging.logger

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "does",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "say",
    "the",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
}

GENAI_RE = re.compile(r"\b(genai|genal|generative\s+ai|generative\s+al)\b", re.IGNORECASE)
LIST_QUERY_WORDS = {
    "architecture",
    "architectures",
    "categories",
    "category",
    "classes",
    "examples",
    "kinds",
    "models",
    "types",
}
LIST_ANCHOR_WORDS = {
    "architectures",
    "categories",
    "category",
    "classes",
    "examples",
    "kinds",
    "types",
}
LIST_ITEM_HINTS = {
    "architecture",
    "architectures",
    "autoencoder",
    "autoencoders",
    "cnn",
    "convolutional",
    "diffusion",
    "gan",
    "gans",
    "gnn",
    "graph neural",
    "gru",
    "lstm",
    "mamba",
    "model",
    "models",
    "network",
    "networks",
    "neural network",
    "rnn",
    "recurrent",
    "transformer",
    "transformers",
    "vae",
    "vaes",
}
SPECIFIC_LIST_ITEM_HINTS = {
    "autoencoder",
    "autoencoders",
    "cnn",
    "convolutional",
    "diffusion",
    "gan",
    "gans",
    "gnn",
    "graph neural",
    "gru",
    "lstm",
    "mamba",
    "recurrent",
    "rnn",
    "transformer",
    "transformers",
    "vae",
    "vaes",
}
LIST_ITEM_START_HINTS = {
    "autoencoder",
    "autoencoders",
    "convolutional",
    "diffusion",
    "generative adversarial",
    "graph",
    "mamba",
    "recurrent",
    "transformer",
    "transformers",
    "variational autoencoder",
}
GENERIC_TITLES = {
    "",
    "deep learning",
    "ocr extracted text",
}


class Retriever:
    def __init__(self):
        self.store = QdrantStore()

    def vector_count(self) -> int:
        count_vectors = getattr(self.store, "count_vectors", None)
        return count_vectors() if callable(count_vectors) else -1

    def vector_store_name(self) -> str:
        return getattr(self.store, "vector_store_name", "unknown")

    def vector_store_backend(self) -> str:
        return getattr(self.store, "vector_store_backend", self.vector_store_name())

    def _tokens(self, text: str) -> List[str]:
        normalized = GENAI_RE.sub("genai generative artificial intelligence", text.lower())
        return [token for token in re.findall(r"[a-zA-Z0-9_]+", normalized) if token not in STOPWORDS and len(token) > 2]

    def _topic_tokens(self, query: str) -> List[str]:
        return [token for token in self._tokens(query) if token not in LIST_QUERY_WORDS]

    def _expanded_query(self, query: str) -> str:
        if not GENAI_RE.search(query):
            return query
        return (
            f"{query} generative artificial intelligence generative ai genai "
            "novel content text audio video pictures code deep learning taxonomy"
        )

    def _normalized_phrase_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (text or "").lower())).strip()

    def _query_phrases(self, query: str) -> List[str]:
        tokens = self._tokens(query)
        phrases: List[str] = []
        if len(tokens) >= 2:
            phrases.append(" ".join(tokens))
        for size in (3, 2):
            if len(tokens) < size:
                continue
            for index in range(0, len(tokens) - size + 1):
                phrase = " ".join(tokens[index : index + size])
                if phrase not in phrases:
                    phrases.append(phrase)
        return phrases

    def _phrase_score(self, query: str, item: Dict[str, Any]) -> float:
        metadata = item.get("metadata", {})
        text = self._normalized_phrase_text(item.get("text") or "")
        file_name = self._normalized_phrase_text(metadata.get("file_name") or "")
        section = self._normalized_phrase_text(metadata.get("section_title") or "")
        title = self._normalized_phrase_text(metadata.get("title") or "")
        caption = self._normalized_phrase_text(metadata.get("caption") or "")
        phrases = self._query_phrases(query)
        if not phrases:
            return 0.0

        score = 0.0
        full_phrase = phrases[0]
        if full_phrase in section or full_phrase in title:
            score += 4.0
        if full_phrase in text:
            score += 3.0
        if full_phrase in file_name:
            score += 2.0

        for phrase in phrases[1:]:
            if phrase in section or phrase in title:
                score += 0.8
            elif phrase in caption or phrase in file_name:
                score += 0.6
            elif phrase in text:
                score += 0.4
        return score

    def _content_quality_score(self, query: str, item: Dict[str, Any]) -> float:
        text = " ".join((item.get("text") or "").split()).lower()
        metadata = item.get("metadata", {})
        chunk_type = (metadata.get("chunk_type") or metadata.get("content_type") or "").lower()
        content = text.split(" content: ", 1)[-1].strip()
        score = 0.0

        if len(content) >= 180:
            score += 1.0
        elif len(content) <= 60:
            score -= 0.8

        if chunk_type in {"diagram_summary", "chart_summary"}:
            score += 1.5
        if chunk_type == "image_description":
            score += 0.5

        if GENAI_RE.search(query):
            if "generative artificial intelligence" in text or "generative ai" in text or "generative al" in text:
                score += 2.5
            if "capable of producing novel content" in text:
                score += 2.0
            if "generative ai is inside deep learning" in text:
                score += 2.0
            if chunk_type == "diagram_summary":
                score += 1.5

        return score

    def _content_body(self, item: Dict[str, Any]) -> str:
        text = " ".join((item.get("text") or "").split())
        return text.split(" Content: ", 1)[-1].strip()

    def _keyword_score(self, query: str, item: Dict[str, Any]) -> float:
        text = (item.get("text") or "").lower()
        metadata = item.get("metadata", {})
        file_name = (metadata.get("file_name") or "").lower()
        section = (metadata.get("section_title") or "").lower()
        title = (metadata.get("title") or "").lower()
        caption = (metadata.get("caption") or "").lower()
        chunk_type = (metadata.get("chunk_type") or metadata.get("content_type") or "").lower()
        visual_type = (metadata.get("visual_type") or "").lower()
        query_lower = query.lower()
        query_tokens = self._tokens(query)
        if not query_tokens:
            return 0.0

        text_hits = sum(1 for token in query_tokens if token in text)
        file_hits = sum(1 for token in query_tokens if token in file_name)
        section_hits = sum(
            1
            for token in query_tokens
            if token in section or token in title or token in caption or token in chunk_type or token in visual_type
        )
        phrase_boost = 1.0 if len(query_lower) > 8 and query_lower in text else 0.0
        phrase_boost += self._phrase_score(query, item)

        return (text_hits / max(len(query_tokens), 1)) + (file_hits * 0.75) + (section_hits * 0.5) + phrase_boost

    def _has_list_item_hint(self, text: str) -> bool:
        normalized = self._normalized_phrase_text(text)
        return any(hint in normalized for hint in LIST_ITEM_HINTS)

    def _has_specific_list_item_hint(self, text: str) -> bool:
        normalized = self._normalized_phrase_text(text)
        return any(hint in normalized for hint in SPECIFIC_LIST_ITEM_HINTS)

    def _starts_like_list_item(self, text: str) -> bool:
        normalized = self._normalized_phrase_text(text)
        return any(normalized.startswith(hint) for hint in LIST_ITEM_START_HINTS)

    def _heading_text(self, item: Dict[str, Any]) -> str:
        metadata = item.get("metadata", {})
        return " ".join(
            str(value or "")
            for value in (
                metadata.get("section_title"),
                metadata.get("title"),
                metadata.get("caption"),
            )
        ).strip()

    def _is_meaningful_list_item(self, item: Dict[str, Any]) -> bool:
        metadata = item.get("metadata", {})
        chunk_type = (metadata.get("chunk_type") or metadata.get("content_type") or "").lower()
        heading = self._heading_text(item)
        normalized_heading = self._normalized_phrase_text(heading)
        heading_words = re.findall(r"[a-zA-Z0-9]+", normalized_heading)
        content = self._content_body(item)
        if not heading or normalized_heading in GENERIC_TITLES:
            return False
        if normalized_heading.startswith("types of ") and len(content) < 180:
            return False
        if chunk_type in {"image_description", "page_ocr", "image_ocr"} and len(content) < 120:
            return False

        concise_heading = 1 <= len(heading_words) <= 8
        specific_heading = self._has_specific_list_item_hint(heading)
        starts_like_item = self._starts_like_list_item(heading)
        if concise_heading and specific_heading:
            return True
        if starts_like_item and len(heading_words) <= 14:
            return True
        return False

    def _file_topic_overlap(self, file_name: str, topic_tokens: List[str]) -> int:
        normalized_file = self._normalized_phrase_text(file_name)
        return sum(1 for token in topic_tokens if token in normalized_file)

    def _anchor_pages_by_file(self, query: str, scored: List[Dict[str, Any]], topic_tokens: List[str]) -> Dict[str, int]:
        anchors: Dict[str, int] = {}
        query_phrases = self._query_phrases(query)
        anchor_phrases = [phrase for phrase in query_phrases if any(word in phrase for word in LIST_ANCHOR_WORDS)]
        for item in scored[:20]:
            metadata = item.get("metadata", {})
            file_name = metadata.get("file_name")
            page_number = metadata.get("page_number")
            if not file_name or page_number is None:
                continue
            haystack = self._normalized_phrase_text(
                " ".join(
                    str(value or "")
                    for value in (
                        metadata.get("section_title"),
                        metadata.get("title"),
                        metadata.get("caption"),
                        item.get("text"),
                    )
                )
            )
            has_list_phrase = any(word in haystack for word in LIST_ANCHOR_WORDS)
            has_query_phrase = any(phrase in haystack for phrase in anchor_phrases)
            topic_hits = sum(1 for token in topic_tokens if token in haystack)
            if (has_list_phrase and topic_hits) or has_query_phrase:
                anchors[str(file_name)] = min(int(page_number), anchors.get(str(file_name), int(page_number)))
        return anchors

    def _list_expansion_candidates(
        self,
        query: str,
        query_filters: Dict[str, Any],
        scored: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not query_filters.get("list_intent"):
            return []

        list_chunks = getattr(self.store, "list_chunks", None)
        if not callable(list_chunks):
            return []

        topic_tokens = self._topic_tokens(query)
        if not topic_tokens:
            return []

        file_scores: Dict[str, float] = {}
        for item in scored[:25]:
            metadata = item.get("metadata", {})
            file_name = metadata.get("file_name")
            if not file_name:
                continue
            overlap = self._file_topic_overlap(str(file_name), topic_tokens)
            keyword = float(item.get("keyword_score") or 0.0)
            file_scores[str(file_name)] = file_scores.get(str(file_name), 0.0) + float(item.get("score") or 0.0) + overlap + keyword

        if query_filters.get("file_name"):
            file_names = [query_filters["file_name"]]
        else:
            file_names = [
                file_name
                for file_name, _ in sorted(file_scores.items(), key=lambda item: item[1], reverse=True)[:2]
            ]
        if not file_names:
            return []

        anchor_pages = self._anchor_pages_by_file(query, scored, topic_tokens)
        expansion: List[Dict[str, Any]] = []
        per_file_limit = max(limit, 200)
        for file_name in file_names:
            try:
                chunks = list_chunks(file_name=file_name, limit=per_file_limit)
            except TypeError:
                chunks = list_chunks(limit=per_file_limit)
            except Exception:
                logger.exception("List expansion failed while reading chunks for %s", file_name)
                continue

            anchor_page = anchor_pages.get(str(file_name))
            if anchor_page is None:
                query_phrases = self._query_phrases(query)
                anchor_phrases = [phrase for phrase in query_phrases if any(word in phrase for word in LIST_ANCHOR_WORDS)]
                for chunk in chunks:
                    metadata = chunk.get("metadata", {})
                    page_number = metadata.get("page_number")
                    if page_number is None:
                        continue
                    haystack = self._normalized_phrase_text(
                        " ".join(
                            str(value or "")
                            for value in (
                                metadata.get("section_title"),
                                metadata.get("title"),
                                metadata.get("caption"),
                                chunk.get("text"),
                            )
                        )
                    )
                    has_query_phrase = any(phrase in haystack for phrase in anchor_phrases)
                    has_list_phrase = any(word in haystack for word in LIST_ANCHOR_WORDS)
                    topic_hits = sum(1 for token in topic_tokens if token in haystack)
                    if has_query_phrase or (has_list_phrase and topic_hits):
                        anchor_page = int(page_number)
                        break

            for chunk in chunks:
                metadata = chunk.get("metadata", {})
                if metadata.get("file_name") != file_name:
                    continue
                if not metadata_matches_filter(metadata, query_filters):
                    continue
                page_number = metadata.get("page_number")
                if anchor_page is not None and page_number is not None:
                    page_distance = int(page_number) - int(anchor_page)
                    if page_distance < 0 or page_distance > 8:
                        continue
                elif self._file_topic_overlap(str(file_name), topic_tokens) == 0:
                    continue

                if not self._is_meaningful_list_item(chunk):
                    continue

                keyword_score = self._keyword_score(query, chunk)
                item_hint = 4.0 if self._has_list_item_hint(self._heading_text(chunk)) else 2.0
                page_bonus = 0.0
                if anchor_page is not None and page_number is not None:
                    page_bonus = max(0.0, 2.0 - (0.15 * abs(int(page_number) - int(anchor_page))))
                metadata_score = metadata_priority_score(metadata, query_filters)
                content_quality_score = self._content_quality_score(query, chunk)
                combined = 8.0 + keyword_score + item_hint + page_bonus + metadata_score + content_quality_score
                expansion.append(
                    {
                        "id": chunk.get("id"),
                        "score": combined,
                        "dense_score": 0.0,
                        "keyword_score": keyword_score,
                        "metadata_score": metadata_score,
                        "content_quality_score": content_quality_score,
                        "rrf_score": 0.0,
                        "lexical_score": combined,
                        "list_expansion_score": combined,
                        "metadata": metadata,
                        "text": chunk.get("text", ""),
                    }
                )

        expansion.sort(
            key=lambda item: (
                item.get("score", 0),
                -int(item.get("metadata", {}).get("page_number") or 0),
            ),
            reverse=True,
        )
        return expansion[:limit]

    def _lexical_candidates(
        self,
        query: str,
        query_filters: Dict[str, Any],
        store_filter: Dict[str, Any],
        limit: int,
    ) -> List[Dict[str, Any]]:
        list_chunks = getattr(self.store, "list_chunks", None)
        if not callable(list_chunks):
            return []

        try:
            chunks = list_chunks(file_name=store_filter.get("file_name"), limit=limit)
        except TypeError:
            chunks = list_chunks(limit=limit)
        except Exception:
            logger.exception("Lexical fallback failed while listing vector chunks")
            return []

        scored: List[Dict[str, Any]] = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            if not metadata_matches_filter(metadata, query_filters):
                continue
            keyword_score = self._keyword_score(query, chunk)
            if keyword_score <= 0:
                continue
            metadata_score = metadata_priority_score(metadata, query_filters)
            content_quality_score = self._content_quality_score(query, chunk)
            combined = metadata_score + (1.15 * keyword_score) + content_quality_score
            scored.append(
                {
                    "id": chunk.get("id"),
                    "score": combined,
                    "dense_score": 0.0,
                    "keyword_score": keyword_score,
                    "metadata_score": metadata_score,
                    "content_quality_score": content_quality_score,
                    "rrf_score": 0.0,
                    "lexical_score": combined,
                    "metadata": metadata,
                    "text": chunk.get("text", ""),
                }
            )

        scored.sort(key=lambda item: item.get("score", 0), reverse=True)
        return scored[: max(config.RETRIEVAL_TOP_K * 3, 30)]

    def _candidate_key(self, item: Dict[str, Any]) -> Any:
        metadata = item.get("metadata", {})
        return item.get("id") or (
            metadata.get("file_name"),
            metadata.get("page_number"),
            metadata.get("chunk_index"),
            (item.get("text") or "")[:120],
        )

    def _merge_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[Any, Dict[str, Any]] = {}
        for item in candidates:
            key = self._candidate_key(item)
            existing = merged.get(key)
            if existing is None:
                merged[key] = dict(item)
                continue

            for score_key in (
                "dense_score",
                "keyword_score",
                "metadata_score",
                "content_quality_score",
                "rrf_score",
                "lexical_score",
            ):
                existing[score_key] = max(float(existing.get(score_key) or 0.0), float(item.get(score_key) or 0.0))
            existing["score"] = max(float(existing.get("score") or 0.0), float(item.get("score") or 0.0))
        return list(merged.values())

    def _merge_debug_scores(self, query: str, hits: List[Dict[str, Any]], query_filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        merged = []
        for rank, hit in enumerate(hits, start=1):
            dense_score = float(hit.get("score") or 0.0)
            keyword_score = self._keyword_score(query, hit)
            metadata_score = metadata_priority_score(hit.get("metadata", {}), query_filters)
            content_quality_score = self._content_quality_score(query, hit)
            rrf_score = 1.0 / (60 + rank)
            combined = metadata_score + dense_score + (0.35 * keyword_score) + content_quality_score + rrf_score
            item = {
                "id": hit.get("id"),
                "score": combined,
                "dense_score": dense_score,
                "keyword_score": keyword_score,
                "metadata_score": metadata_score,
                "content_quality_score": content_quality_score,
                "rrf_score": rrf_score,
                "metadata": hit.get("metadata", {}),
                "text": hit.get("text", ""),
            }
            merged.append(item)
        return merged

    def _log_hits(self, label: str, hits: List[Dict[str, Any]]) -> None:
        if not config.DEBUG_RETRIEVAL_SCORES:
            return
        logger.info("%s", label)
        for index, item in enumerate(hits, start=1):
            metadata = item.get("metadata", {})
            preview = " ".join((item.get("text") or "").split())[:180]
            logger.info(
                "%s. %s | year=%s | page=%s | score=%s | dense=%s | keyword=%s | preview=%s",
                index,
                metadata.get("file_name"),
                metadata.get("year"),
                metadata.get("page_number"),
                item.get("score"),
                item.get("dense_score"),
                item.get("keyword_score"),
                preview,
            )

    def retrieve(self, query: str, top_k: int | None = None, query_filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        top_k = top_k or config.RETRIEVAL_TOP_K
        query_filters = query_filters or parse_query_filters(query)
        vector_count = self.vector_count()

        if vector_count == 0:
            logger.warning(
                "Retriever vector store is empty before search; store=%s backend=%s collection=%s. Retrying vector store connection.",
                self.vector_store_name(),
                self.vector_store_backend(),
                config.QDRANT_COLLECTION,
            )
            reconnect = getattr(self.store, "reconnect", None)
            if callable(reconnect) and reconnect():
                vector_count = self.vector_count()
                logger.info(
                    "Retriever reconnected to store=%s backend=%s with vector_count=%s.",
                    self.vector_store_name(),
                    self.vector_store_backend(),
                    vector_count,
                )

        if vector_count == 0:
            logger.warning(
                "Retriever cannot search because no vectors are available; store=%s backend=%s collection=%s.",
                self.vector_store_name(),
                self.vector_store_backend(),
                config.QDRANT_COLLECTION,
            )
            return []

        store_filter = {}
        if query_filters.get("year") is not None:
            store_filter["year"] = query_filters["year"]
        if query_filters.get("file_name"):
            store_filter["file_name"] = query_filters["file_name"]
        if query_filters.get("page_number") is not None:
            store_filter["page_number"] = query_filters["page_number"]
        if query_filters.get("figure_number"):
            store_filter["figure_number"] = query_filters["figure_number"]

        if config.DEBUG_RETRIEVAL_SCORES:
            logger.info(
                "QUERY FILTERS: year=%s quarter=%s metrics=%s document_type=%s file_name=%s page=%s figure=%s visual=%s chart=%s diagram=%s",
                query_filters.get("year"),
                query_filters.get("quarter"),
                query_filters.get("metrics"),
                query_filters.get("document_type"),
                query_filters.get("file_name"),
                query_filters.get("page_number"),
                query_filters.get("figure_number"),
                query_filters.get("visual"),
                query_filters.get("chart_intent"),
                query_filters.get("diagram_intent"),
            )

        # Retrieve more than we need, then let lexical boosts and reranking improve precision.
        expanded_query = self._expanded_query(query)
        search_k = max(top_k * 5, 50) if query_filters.get("visual") or query_filters.get("genai_topic") else max(top_k * 3, 20)
        dense_hits = self.store.search(expanded_query, top_k=search_k, filter=store_filter or None)
        logger.info(
            "Retrieved %s dense hits for query; store=%s backend=%s vector_count=%s.",
            len(dense_hits),
            self.vector_store_name(),
            self.vector_store_backend(),
            vector_count,
        )
        scored = self._merge_debug_scores(expanded_query, dense_hits, query_filters)
        lexical_limit = min(max(vector_count if vector_count > 0 else search_k, search_k), 2000)
        lexical = self._lexical_candidates(query, query_filters, store_filter, lexical_limit)
        if lexical:
            logger.info("Retrieved %s lexical fallback hits for query.", len(lexical))
        list_expansion = self._list_expansion_candidates(query, query_filters, scored + lexical, max(top_k * 3, 30))
        if list_expansion:
            logger.info("Retrieved %s list expansion hits for query.", len(list_expansion))
        scored = self._merge_candidates(scored + lexical + list_expansion)
        self._log_hits("RETRIEVED BEFORE RERANK:", scored)

        filtered = [
            item
            for item in scored
            if item["dense_score"] >= config.MIN_RETRIEVAL_SCORE or item["keyword_score"] > 0
        ]
        if not filtered:
            filtered = scored

        filtered.sort(key=lambda item: item.get("score", 0), reverse=True)
        return filtered[: max(top_k * 2, top_k)]
