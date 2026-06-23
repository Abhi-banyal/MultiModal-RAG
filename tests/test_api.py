import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


client = TestClient(app)


def test_app_startup_and_health(monkeypatch):
    class DummyStore:
        vector_store_name = "local"

        def count_vectors(self):
            return 0

    monkeypatch.setattr("app.api.routes.QdrantStore", lambda: DummyStore())

    # The health response includes runtime vector metadata.
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "vector_count" in response.json()


def test_chat_endpoint_fallback(monkeypatch):
    class DummyGraph:
        def run(self, question):
            return "", []

    monkeypatch.setattr("app.api.routes.RAGGraph", lambda: DummyGraph())

    response = client.post("/chat", json={"question": "What is in the report?"})
    assert response.status_code == 200
    assert response.json()["answer"] == "I could not find this information in the uploaded documents."
    assert response.json()["sources"] == []


def test_visual_endpoint_serves_source_image():
    response = client.get("/visuals/cnn_diagram.png")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert len(response.content) > 100


def test_visual_endpoint_can_crop_pdf_visual_region():
    full_response = client.get("/visuals/company_chart.pdf?page_number=1")
    cropped_response = client.get("/visuals/company_chart.pdf?page_number=1&crop=visual")

    assert full_response.status_code == 200
    assert cropped_response.status_code == 200

    full_image = Image.open(io.BytesIO(full_response.content))
    cropped_image = Image.open(io.BytesIO(cropped_response.content))

    assert cropped_image.width < full_image.width
    assert cropped_image.height < full_image.height
    assert cropped_image.width > 100
    assert cropped_image.height > 100


def test_visual_endpoint_does_not_return_full_page_when_no_visual_region():
    response = client.get("/visuals/company_policy.pdf?page_number=4&crop=visual")

    assert response.status_code == 404


def test_visual_endpoint_rejects_path_traversal():
    response = client.get("/visuals/..%2F.env")

    assert response.status_code in {400, 404}


def test_ingest_endpoint_reports_warning_response(monkeypatch):
    class DummyService:
        def ingest_all(self, force=False, reset=False):
            return {
                "status": "completed_with_warnings",
                "vector_store": "qdrant_local",
                "collection": "multimodal_rag",
                "total_files": 2,
                "processed_files": ["ok.txt"],
                "failed_files": [],
                "skipped_files": [{"file_name": "blank.png", "file_path": "/tmp/blank.png", "message": "no extractable text"}],
                "total_chunks_created": 1,
                "vectors_stored": 1,
                "vector_store_count_after_ingest": 1,
                "warnings": [{"file_name": "blank.png", "file_path": "/tmp/blank.png", "message": "no extractable text"}],
                "errors": [],
            }

    monkeypatch.setattr("app.api.routes.IngestionService", lambda: DummyService())

    response = client.post("/ingest")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed_with_warnings"
    assert body["processed_files"] == ["ok.txt"]
    assert body["vectors_stored"] == 1
    assert body["skipped_files"][0]["file_name"] == "blank.png"


def test_ingest_endpoint_returns_500_when_all_files_fail(monkeypatch):
    class DummyService:
        def ingest_all(self, force=False, reset=False):
            return {
                "status": "failed",
                "vector_store": "qdrant_local",
                "collection": "multimodal_rag",
                "total_files": 1,
                "processed_files": [],
                "failed_files": [{"file_name": "bad.pdf", "file_path": "/tmp/bad.pdf", "message": "broken"}],
                "skipped_files": [],
                "total_chunks_created": 0,
                "vectors_stored": 0,
                "vector_store_count_after_ingest": 0,
                "warnings": [],
                "errors": [{"file_name": "bad.pdf", "file_path": "/tmp/bad.pdf", "message": "broken"}],
            }

    monkeypatch.setattr("app.api.routes.IngestionService", lambda: DummyService())

    response = client.post("/ingest")

    assert response.status_code == 500
    assert response.json()["status"] == "failed"
    assert response.json()["failed_files"][0]["file_name"] == "bad.pdf"
