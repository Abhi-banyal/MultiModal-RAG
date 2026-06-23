from __future__ import annotations

from typing import Any, Dict, List, Tuple, TypedDict

from ..core import config, logging
from .answer_generator import AnswerGenerator
from .query_parser import parse_query_filters
from .reranker import Reranker
from .retriever import Retriever

logger = logging.logger

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - optional dependency in lean environments
    END = None
    StateGraph = None


class RAGState(TypedDict, total=False):
    question: str
    query: str
    query_filters: Dict[str, Any]
    candidates: List[Dict[str, Any]]
    ranked: List[Dict[str, Any]]
    context_chunks: List[Dict[str, Any]]
    answer: str
    sources: List[Dict[str, Any]]
    needs_clarification: bool


class RAGGraph:
    def __init__(self):
        self.retriever = Retriever()
        self.reranker = Reranker()
        self.generator = AnswerGenerator()
        self.graph = self._build_graph() if StateGraph is not None else None


        print("langGraph working:", self.graph is not None)
        print("Graph object:", type(self.graph))

    def _retriever_vector_count(self) -> int:
        vector_count = getattr(self.retriever, "vector_count", None)
        return vector_count() if callable(vector_count) else -1

    def _retriever_store_name(self) -> str:
        store_name = getattr(self.retriever, "vector_store_name", None)
        return store_name() if callable(store_name) else "unknown"

    def _retriever_backend_name(self) -> str:
        backend_name = getattr(self.retriever, "vector_store_backend", None)
        return backend_name() if callable(backend_name) else self._retriever_store_name()

    def _receive_question(self, state: Dict[str, Any]) -> Dict[str, Any]:
        question = (state.get("question") or "").strip()
        return {**state, "question": question, "query": question}

    def _rewrite_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        query = (state.get("query") or state.get("question") or "").strip()
        query_filters = parse_query_filters(query)
        return {**state, "query": query, "query_filters": query_filters}

    def _retrieve_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        vector_count = self._retriever_vector_count()
        logger.info(
            "Chat retrieval started; question=%r store=%s backend=%s vector_count=%s",
            state.get("question"),
            self._retriever_store_name(),
            self._retriever_backend_name(),
            vector_count,
        )
        try:
            candidates = self.retriever.retrieve(
                state["query"],
                top_k=config.RETRIEVAL_TOP_K,
                query_filters=state.get("query_filters"),
            )
        except TypeError:
            candidates = self.retriever.retrieve(state["query"], top_k=config.RETRIEVAL_TOP_K)
        vector_count = self._retriever_vector_count()
        logger.info("Chat retrieval completed; candidates=%s vector_count=%s", len(candidates), vector_count)
        return {
            **state,
            "candidates": candidates,
            "vector_count": vector_count,
            "vector_store_backend": self._retriever_backend_name(),
        }

    def _rerank_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        ranked = self.reranker.rerank(state["query"], state.get("candidates", []))
        logger.info(
            "Chat rerank completed; ranked=%s sources=%s",
            len(ranked),
            sorted(
                {
                    item.get("metadata", {}).get("file_name")
                    for item in ranked
                    if item.get("metadata", {}).get("file_name")
                }
            ),
        )
        return {**state, "ranked": ranked}

    def _maybe_ask_clarification(self, state: Dict[str, Any]) -> Dict[str, Any]:
        query_filters = state.get("query_filters") or {}
        if not query_filters.get("needs_year_clarification"):
            return state

        years = {
            item.get("metadata", {}).get("year")
            for item in state.get("ranked", []) or state.get("candidates", [])
            if item.get("metadata", {}).get("year") is not None
        }
        if len(years) > 1:
            choices = " or ".join(str(year) for year in sorted(years))
            return {
                **state,
                "answer": f"Please specify which year you mean ({choices}) so I do not mix results from different documents.",
                "sources": [],
                "needs_clarification": True,
            }
        return state

    def _build_context_chunks(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if state.get("needs_clarification"):
            return {**state, "context_chunks": []}
        ranked = state.get("ranked", [])
        context_chunks = [
            {
                "id": item.get("id"),
                "text": item.get("text", ""),
                "metadata": item.get("metadata", {}),
                "score": item.get("score"),
                "dense_score": item.get("dense_score"),
                "keyword_score": item.get("keyword_score"),
                "rerank_score": item.get("rerank_score"),
                "final_score": item.get("final_score"),
            }
            for item in ranked
        ]
        context_length = sum(len(item.get("text") or "") for item in context_chunks)
        logger.info("Chat context prepared; chunks=%s context_chars=%s", len(context_chunks), context_length)
        if config.DEBUG_RETRIEVAL_SCORES:
            logger.info("FINAL CHUNKS SENT TO LLM:")
            for index, item in enumerate(context_chunks, start=1):
                metadata = item.get("metadata", {})
                preview = " ".join((item.get("text") or "").split())[:180]
                logger.info(
                    "%s. %s | year=%s | page=%s | score=%s | rerank=%s | preview=%s",
                    index,
                    metadata.get("file_name"),
                    metadata.get("year"),
                    metadata.get("page_number"),
                    item.get("score"),
                    item.get("rerank_score"),
                    preview,
                )
        return {**state, "context_chunks": context_chunks}

    def _generate_answer(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if state.get("needs_clarification"):
            return state
        answer, sources = self.generator.generate(state["question"], state.get("context_chunks", []))
        logger.info("Chat answer generated; answer_chars=%s sources=%s", len(answer or ""), len(sources or []))
        return {**state, "answer": answer, "sources": sources}

    def _validate_answer(self, state: Dict[str, Any]) -> Dict[str, Any]:
        answer = (state.get("answer") or "").strip()
        if not answer:
            if int(state.get("vector_count") or 0) == 0 and state.get("vector_store_backend") == "json_fallback":
                answer = (
                    "The indexed vector store is temporarily unavailable. "
                    "Restart the backend and make sure only one Uvicorn process is using the local Qdrant store."
                )
            elif int(state.get("vector_count") or 0) == 0:
                answer = "No indexed documents found. Please ingest documents first."
            elif not state.get("candidates") or not state.get("ranked"):
                answer = "No relevant context found in the indexed documents."
            else:
                answer = "I could not find this information in the uploaded documents."
            sources = []
        else:
            sources = state.get("sources", [])
        return {**state, "answer": answer, "sources": sources}

    def _build_graph(self):
        workflow = StateGraph(RAGState)
        workflow.add_node("receive_question", self._receive_question)
        workflow.add_node("rewrite_query", self._rewrite_query)
        workflow.add_node("retrieve_context", self._retrieve_context)
        workflow.add_node("rerank_context", self._rerank_context)
        workflow.add_node("maybe_ask_clarification", self._maybe_ask_clarification)
        workflow.add_node("build_context_chunks", self._build_context_chunks)
        workflow.add_node("generate_answer", self._generate_answer)
        workflow.add_node("validate_answer", self._validate_answer)

        workflow.set_entry_point("receive_question")
        workflow.add_edge("receive_question", "rewrite_query")
        workflow.add_edge("rewrite_query", "retrieve_context")
        workflow.add_edge("retrieve_context", "rerank_context")
        workflow.add_edge("rerank_context", "maybe_ask_clarification")
        workflow.add_edge("maybe_ask_clarification", "build_context_chunks")
        workflow.add_edge("build_context_chunks", "generate_answer")
        workflow.add_edge("generate_answer", "validate_answer")
        workflow.add_edge("validate_answer", END)
        return workflow.compile()

    def _run_without_langgraph(self, question: str) -> Tuple[str, List[Dict[str, Any]]]:
        state: Dict[str, Any] = {"question": question}
        for step in (
            self._receive_question,
            self._rewrite_query,
            self._retrieve_context,
            self._rerank_context,
            self._maybe_ask_clarification,
            self._build_context_chunks,
            self._generate_answer,
            self._validate_answer,
        ):
            state = step(state)
        return state.get("answer", ""), state.get("sources", [])

    def run(self, question: str) -> Tuple[str, List[Dict[str, Any]]]:
        if self.graph is None:
            return self._run_without_langgraph(question)

        state = self.graph.invoke({"question": question})
        return state.get("answer", ""), state.get("sources", [])

    def debug_search(self, question: str) -> List[Dict[str, Any]]:
        query_filters = parse_query_filters(question)
        try:
            candidates = self.retriever.retrieve(question, top_k=config.RETRIEVAL_TOP_K, query_filters=query_filters)
        except TypeError:
            candidates = self.retriever.retrieve(question, top_k=config.RETRIEVAL_TOP_K)
        ranked = self.reranker.rerank(question, candidates)
        return ranked
