from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingestion.ingestion_service import IngestionService
from app.rag.graph import RAGGraph
from app.vectorstores.qdrant_store import QdrantStore


def assert_condition(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"OK: {message}")


def main() -> None:
    ingest_result = IngestionService().ingest_all()
    print("Ingest result:", ingest_result)
    assert_condition(ingest_result["status"] in {"completed", "completed_with_warnings"}, "ingest runs without crashing")

    store = QdrantStore()
    vector_count = store.count_vectors()
    assert_condition(vector_count > 0, "vector count is greater than 0 after ingest")

    policy_chunks = store.list_chunks(file_name="company_policy.pdf", limit=500)
    assert_condition(bool(policy_chunks), "company_policy.pdf chunks exist")

    graph = RAGGraph()

    policy_query = "What does the Data security and IT usage policy say about passwords?"
    policy_hits = graph.debug_search(policy_query)
    top_policy_files = [hit.get("metadata", {}).get("file_name") for hit in policy_hits[:3]]
    print("Policy top files:", top_policy_files)
    assert_condition("company_policy.pdf" in top_policy_files, "password policy query retrieves company_policy.pdf")

    revenue_query = "What was the revenue in 2024 Q1?"
    revenue_hits = graph.debug_search(revenue_query)
    top_revenue_files = [hit.get("metadata", {}).get("file_name") for hit in revenue_hits[:5]]
    print("Revenue top files:", top_revenue_files)
    assert_condition(
        any(name in {"company_chart.pdf", "company_report.pdf"} for name in top_revenue_files),
        "revenue query retrieves company_chart.pdf or company_report.pdf",
    )

    answer, sources = graph.run(revenue_query)
    print("Revenue answer:", answer)
    print("Sources:", sources)
    assert_condition(bool(answer.strip()), "final answer is non-empty")
    if "12.0" in " ".join(hit.get("text", "") for hit in revenue_hits[:5]):
        assert_condition("12.0" in answer or "12" in answer, "final answer includes the revenue value when present in context")


if __name__ == "__main__":
    main()
