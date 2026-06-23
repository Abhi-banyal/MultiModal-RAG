import os
from pathlib import Path
import json
import tempfile
import pytest

from app.ingestion.chunker import split_text_to_chunks, create_chunk_docs
from app.utils.file_hash import file_hash
from app.ingestion.ingestion_service import IngestionService


def test_split_text_to_chunks():
    text = "Paragraph one.\n\nParagraph two has more content. " * 5
    chunks = split_text_to_chunks(text, chunk_size=100, overlap=20)
    assert len(chunks) >= 2


def test_file_hash(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello")
    h1 = file_hash(p)
    p.write_text("hello2")
    h2 = file_hash(p)
    assert h1 != h2


def test_ingestion_service_txt_and_image(tmp_path, monkeypatch):
    # prepare data dir
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    txt = data_dir / "test.txt"
    txt.write_text("This is a test document. It contains a chart description.")

    # create a small image
    from PIL import Image
    img = Image.new("RGB", (100, 50), color=(73, 109, 137))
    img_path = data_dir / "img.png"
    img.save(img_path)

    # monkeypatch config.DATA_DIR and QdrantStore.upsert_documents
    from app.core import config
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "INDEX_METADATA_PATH", tmp_path / ".index_meta.json")

    called = {"upserted": 0}

    class DummyStore:
        vector_store_name = "local"
        embedding_dim = 384

        def upsert_documents(self, docs):
            called["upserted"] += len(docs)

        def clear_collection(self):
            return

        def count_file_vectors(self, file_hash):
            return 0

        def delete_file_vectors(self, file_hash):
            return

        def count_vectors(self):
            return called["upserted"]

    monkeypatch.setattr("app.ingestion.ingestion_service.QdrantStore", lambda: DummyStore())

    svc = IngestionService()
    res = svc.ingest_all()
    assert res["total_files"] == 2
    assert res["files_processed"] >= 1
    assert "successful_files" in res
    assert "processed_files" in res
    assert "failed_files" in res
    assert "skipped_files" in res
    assert "total_chunks" in res
    assert "total_chunks_created" in res
    assert "vectors_stored" in res
    assert called["upserted"] >= 1


def test_ingestion_skips_unreadable_empty_image_text(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    img_path = data_dir / "blank.png"

    from PIL import Image
    Image.new("RGB", (100, 50), color="white").save(img_path)

    from app.core import config
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "INDEX_METADATA_PATH", tmp_path / ".index_meta.json")
    monkeypatch.setattr(config, "USE_OPENAI_VISION", False)

    class DummyStore:
        vector_store_name = "local"
        embedding_dim = 384

        def upsert_documents(self, docs):
            raise AssertionError("blank images should be skipped, not stored")

        def clear_collection(self):
            return

        def count_file_vectors(self, file_hash):
            return 0

        def delete_file_vectors(self, file_hash):
            return

        def count_vectors(self):
            return 0

    monkeypatch.setattr("app.ingestion.ingestion_service.QdrantStore", lambda: DummyStore())
    monkeypatch.setattr("app.ingestion.vision_processor.ocr_image", lambda image: "")

    svc = IngestionService()
    res = svc.ingest_all()

    assert res["status"] == "completed_with_warnings"
    assert res["skipped_files"][0]["file_name"] == "blank.png"
    assert res["vectors_stored"] == 0


def test_openai_vision_failure_falls_back_to_ocr(monkeypatch):
    from PIL import Image
    from app.core import config
    from app.ingestion.vision_processor import process_image

    monkeypatch.setattr(config, "USE_OPENAI_VISION", True)
    monkeypatch.setattr("app.ingestion.vision_processor.ocr_image", lambda image: "hello from OCR")

    def fail_vision(image):
        raise RuntimeError("insufficient_quota")

    monkeypatch.setattr("app.ingestion.vision_processor._describe_with_vision_model", fail_vision)

    result = process_image(Image.new("RGB", (50, 30), color="white"))

    assert "hello from OCR" in result.text
    assert result.extraction_method == "image_ocr"
    assert result.warnings
