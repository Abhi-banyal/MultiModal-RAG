from app.ingestion.chunker import create_chunk_docs, split_text_to_chunks
from app.ingestion.metadata_extractor import infer_visual_type
from app.rag.graph import RAGGraph
from app.rag.retriever import Retriever
from app.rag.query_parser import parse_query_filters


def test_chunk_docs_include_required_metadata():
    docs = create_chunk_docs(
        {
            "source_file": "sample.pdf",
            "file_name": "sample.pdf",
            "file_path": "/tmp/sample.pdf",
            "file_type": "pdf",
            "page_number": 2,
        },
        ["Chunk text"],
        "text",
    )

    assert len(docs) == 1
    metadata = docs[0]["metadata"]
    assert metadata["source_file"] == "sample.pdf"
    assert metadata["file_path"] == "/tmp/sample.pdf"
    assert metadata["file_type"] == "pdf"
    assert metadata["page_number"] == 2
    assert metadata["content_type"] == "text"
    assert "source_path" in metadata
    assert "year" in metadata
    assert "document_type" in metadata
    assert "quarter" in metadata
    assert "metric_names" in metadata
    assert "title" in metadata
    assert metadata["chunk_id"]


def test_chunk_docs_extract_year_quarter_metrics():
    docs = create_chunk_docs(
        {
            "source_file": "company_chart.pdf",
            "file_name": "company_chart.pdf",
            "file_path": "/tmp/company_chart.pdf",
            "file_type": "pdf",
            "page_number": 1,
        },
        ["Company Quarterly Results Chart\nQ4 2024 revenue: 140M, net profit: 30M"],
        "chart_summary",
    )

    metadata = docs[0]["metadata"]
    assert metadata["year"] == 2024
    assert metadata["quarter"] == "Q4"
    assert metadata["metric_names"] == ["revenue", "net_profit"]
    assert metadata["document_type"] == "chart"


def test_query_parser_detects_year_quarter_metric():
    filters = parse_query_filters("What was the revenue in Q4 2024?")

    assert filters["year"] == 2024
    assert filters["quarter"] == "Q4"
    assert filters["metrics"] == ["revenue"]


def test_query_parser_detects_visual_intent():
    filters = parse_query_filters("Explain Figure 1 in genai.pdf")

    assert filters["file_name"] == "genai.pdf"
    assert filters["figure_number"] == "1"
    assert filters["visual"] is True
    assert filters["diagram_intent"] is True


def test_query_parser_does_not_treat_workflow_as_visual_flow():
    filters = parse_query_filters("what is Machine Learning Workflow")

    assert filters["visual"] is False
    assert filters["diagram_intent"] is False
    assert filters["chart_intent"] is False


def test_query_parser_detects_list_intent():
    filters = parse_query_filters("Types of deep learning")

    assert filters["list_intent"] is True
    assert "deep" in filters["topic_terms"]
    assert "learning" in filters["topic_terms"]


def test_metadata_does_not_treat_workflow_as_visual_flow():
    assert infer_visual_type("Machine Learning Workflow\nData Collection: Gather raw data.", "txt") == ""


def test_retriever_preserves_text(monkeypatch):
    class DummyStore:
        def search(self, query, top_k=5, filter=None):
            return [{"id": "1", "score": 1.0, "metadata": {"file_name": "a.txt"}, "text": "retrieved text"}]

    monkeypatch.setattr("app.rag.retriever.QdrantStore", lambda: DummyStore())
    retriever = Retriever()

    results = retriever.retrieve("hello")
    assert results[0]["text"] == "retrieved text"


def test_retriever_applies_year_filter_for_2024(monkeypatch):
    calls = {}

    class DummyStore:
        def search(self, query, top_k=5, filter=None):
            calls["filter"] = filter
            return [
                {
                    "id": "chart",
                    "score": 0.8,
                    "metadata": {
                        "file_name": "company_chart.pdf",
                        "year": 2024,
                        "quarter": "Q4",
                        "metric_names": ["revenue", "net_profit"],
                    },
                    "text": "Q4 2024 revenue: 140M, net profit: 30M",
                }
            ]

    monkeypatch.setattr("app.rag.retriever.QdrantStore", lambda: DummyStore())
    retriever = Retriever()

    results = retriever.retrieve("What was the revenue in Q4 2024?")

    assert calls["filter"] == {"year": 2024}
    assert results[0]["metadata"]["file_name"] == "company_chart.pdf"


def test_retriever_applies_year_filter_for_2025(monkeypatch):
    calls = {}

    class DummyStore:
        def search(self, query, top_k=5, filter=None):
            calls["filter"] = filter
            return [
                {
                    "id": "report",
                    "score": 0.8,
                    "metadata": {
                        "file_name": "company_report.pdf",
                        "year": 2025,
                        "quarter": "Q4",
                        "metric_names": ["revenue", "net_profit"],
                    },
                    "text": "Q4 2025 revenue: 18.0M, net profit: 4.5M",
                }
            ]

    monkeypatch.setattr("app.rag.retriever.QdrantStore", lambda: DummyStore())
    retriever = Retriever()

    results = retriever.retrieve("What was the revenue in Q4 2025?")

    assert calls["filter"] == {"year": 2025}
    assert results[0]["metadata"]["file_name"] == "company_report.pdf"


def test_visual_query_prioritizes_diagram_summary(monkeypatch):
    class DummyStore:
        def search(self, query, top_k=5, filter=None):
            return [
                {
                    "id": "text",
                    "score": 0.9,
                    "metadata": {"file_name": "genai.pdf", "content_type": "pdf_text", "chunk_type": "pdf_text"},
                    "text": "Figure 1: A taxonomy of GenAI-related disciplines.",
                },
                {
                    "id": "diagram",
                    "score": 0.6,
                    "metadata": {
                        "file_name": "genai.pdf",
                        "content_type": "diagram_summary",
                        "chunk_type": "diagram_summary",
                        "title": "A taxonomy of GenAI-related disciplines",
                        "contains_diagram": True,
                        "visual_type": "taxonomy",
                    },
                    "text": "Artificial Intelligence contains Machine Learning, which contains Deep Learning and Generative AI.",
                },
            ]

    monkeypatch.setattr("app.rag.retriever.QdrantStore", lambda: DummyStore())
    retriever = Retriever()

    results = retriever.retrieve("What is taxonomy of GenAI-related disciplines?")

    assert results[0]["metadata"]["chunk_type"] == "diagram_summary"


def test_genai_query_prioritizes_answer_bearing_definition(monkeypatch):
    class DummyStore:
        def search(self, query, top_k=5, filter=None):
            assert "generative artificial intelligence" in query.lower()
            return [
                {
                    "id": "label",
                    "score": 0.95,
                    "metadata": {
                        "file_name": "genai.pdf",
                        "content_type": "page_ocr",
                        "chunk_type": "page_ocr",
                        "title": "Artificial Intelligence",
                    },
                    "text": "Document: genai.pdf\nContent:\nArtificial Intelligence",
                },
                {
                    "id": "definition",
                    "score": 0.7,
                    "metadata": {
                        "file_name": "genai.pdf",
                        "content_type": "pdf_text",
                        "chunk_type": "pdf_text",
                        "title": "Generative artificial intelligence (GenAI) tools are an emerging class",
                    },
                    "text": (
                        "Document: genai.pdf\nContent:\nGenerative artificial intelligence (GenAI) tools "
                        "are an emerging class of artificial intelligence algorithms capable of producing "
                        "novel content in formats such as text, audio, video, pictures, and code."
                    ),
                },
            ]

    monkeypatch.setattr("app.rag.retriever.QdrantStore", lambda: DummyStore())
    retriever = Retriever()

    results = retriever.retrieve("what is genai")

    assert results[0]["id"] == "definition"


def test_retriever_exact_section_match_beats_visual_semantic_match(monkeypatch):
    workflow_chunk = {
        "id": "workflow",
        "score": 0.0,
        "metadata": {
            "file_name": "machine_learning.txt",
            "content_type": "text",
            "chunk_type": "text",
            "section_title": "Machine Learning Workflow",
            "title": "Machine Learning Workflow",
            "document_type": "txt",
        },
        "text": (
            "Document: machine_learning.txt\n"
            "Section: Machine Learning Workflow\n"
            "Content:\n"
            "Machine Learning Workflow\n"
            "Data Collection: Gathering raw data from various sources.\n"
            "Model Selection: Choosing the appropriate algorithm for the task."
        ),
    }

    visual_chunk = {
        "id": "diagram",
        "score": 0.92,
        "metadata": {
            "file_name": "genai.pdf",
            "content_type": "diagram_summary",
            "chunk_type": "diagram_summary",
            "title": "A taxonomy of GenAI-related disciplines",
            "contains_diagram": True,
            "visual_type": "taxonomy",
        },
        "text": "Artificial Intelligence contains Machine Learning, which contains Deep Learning and Generative AI.",
    }

    class DummyStore:
        def count_vectors(self):
            return 2

        def search(self, query, top_k=5, filter=None):
            return [visual_chunk]

        def list_chunks(self, file_name=None, limit=200):
            return [visual_chunk, workflow_chunk]

    monkeypatch.setattr("app.rag.retriever.QdrantStore", lambda: DummyStore())
    retriever = Retriever()

    results = retriever.retrieve("what is Machine Learning Workflow", top_k=2)

    assert results[0]["id"] == "workflow"
    assert results[0]["metadata"]["file_name"] == "machine_learning.txt"


def test_retriever_expands_list_query_to_neighbor_model_chunks(monkeypatch):
    heading = {
        "id": "heading",
        "score": 0.9,
        "metadata": {
            "file_name": "deep_learning.pdf",
            "page_number": 4,
            "content_type": "pdf_text",
            "chunk_type": "pdf_text",
            "section_title": "Types of deep learning models",
            "title": "Types of deep learning models",
        },
        "text": "Document: deep_learning.pdf\nPage: 4\nContent:\nTypes of deep learning models",
    }
    cnn = {
        "id": "cnn",
        "score": 0.8,
        "metadata": {
            "file_name": "deep_learning.pdf",
            "page_number": 5,
            "content_type": "pdf_text",
            "chunk_type": "pdf_text",
            "section_title": "Convolutional neural networks (CNNs)",
            "title": "Convolutional neural networks (CNNs)",
        },
        "text": (
            "Document: deep_learning.pdf\nPage: 5\nContent:\n"
            "Convolutional neural networks (CNNs) are used for computer vision tasks and local pattern recognition."
        ),
    }
    rnn = {
        "id": "rnn",
        "score": 0.0,
        "metadata": {
            "file_name": "deep_learning.pdf",
            "page_number": 6,
            "content_type": "pdf_text",
            "chunk_type": "pdf_text",
            "section_title": "Recurrent neural networks (RNNs)",
            "title": "Recurrent neural networks (RNNs)",
        },
        "text": (
            "Document: deep_learning.pdf\nPage: 6\nContent:\n"
            "Recurrent neural networks (RNNs) are used for sequential data such as time-series forecasting, "
            "speech recognition, and natural language processing."
        ),
    }
    autoencoder = {
        "id": "autoencoder",
        "score": 0.0,
        "metadata": {
            "file_name": "deep_learning.pdf",
            "page_number": 8,
            "content_type": "pdf_text",
            "chunk_type": "pdf_text",
            "section_title": "Autoencoders",
            "title": "Autoencoders",
        },
        "text": (
            "Document: deep_learning.pdf\nPage: 8\nContent:\n"
            "Autoencoders compress input data and reconstruct the original input from the compressed representation."
        ),
    }

    class DummyStore:
        def count_vectors(self):
            return 4

        def search(self, query, top_k=5, filter=None):
            return [heading, cnn]

        def list_chunks(self, file_name=None, limit=200):
            assert file_name in {None, "deep_learning.pdf"}
            return [heading, cnn, rnn, autoencoder]

    monkeypatch.setattr("app.rag.retriever.QdrantStore", lambda: DummyStore())
    retriever = Retriever()

    results = retriever.retrieve("Types of deep learning", top_k=4)

    result_ids = [item["id"] for item in results]
    assert "rnn" in result_ids
    assert "autoencoder" in result_ids


def test_rag_graph_asks_clarification_when_metric_year_missing(monkeypatch):
    class DummyRetriever:
        def retrieve(self, query, top_k=8, query_filters=None):
            return [
                {
                    "id": "chart",
                    "score": 2.0,
                    "text": "Q4 2024 revenue: 140M",
                    "metadata": {"file_name": "company_chart.pdf", "year": 2024, "content_type": "chart_summary"},
                },
                {
                    "id": "report",
                    "score": 1.9,
                    "text": "Q4 2025 revenue: 18.0M",
                    "metadata": {"file_name": "company_report.pdf", "year": 2025, "content_type": "text"},
                },
            ]

    class DummyReranker:
        def rerank(self, query, candidates):
            return candidates

    class DummyGenerator:
        def generate(self, question, context_chunks):
            raise AssertionError("ambiguous year questions should not reach answer generation")

    monkeypatch.setattr("app.rag.graph.Retriever", lambda: DummyRetriever())
    monkeypatch.setattr("app.rag.graph.Reranker", lambda: DummyReranker())
    monkeypatch.setattr("app.rag.graph.AnswerGenerator", lambda: DummyGenerator())

    graph = RAGGraph()
    answer, sources = graph.run("What was the revenue in Q4?")

    assert "Please specify which year" in answer
    assert sources == []


def test_langgraph_run_returns_grounded_answer(monkeypatch):
    class DummyRetriever:
        def retrieve(self, query, top_k=8):
            return [
                {
                    "id": "1",
                    "score": 1.0,
                    "text": "The report says the revenue increased.",
                    "metadata": {"file_name": "report.pdf", "page_number": 3, "content_type": "text"},
                }
            ]

    class DummyReranker:
        def rerank(self, query, candidates):
            return candidates

    class DummyGenerator:
        def generate(self, question, context_chunks):
            return ("The report says the revenue increased.", [{"file_name": "report.pdf", "page_number": 3, "content_type": "text"}])

    monkeypatch.setattr("app.rag.graph.Retriever", lambda: DummyRetriever())
    monkeypatch.setattr("app.rag.graph.Reranker", lambda: DummyReranker())
    monkeypatch.setattr("app.rag.graph.AnswerGenerator", lambda: DummyGenerator())

    graph = RAGGraph()
    answer, sources = graph.run("What happened to revenue?")

    assert "revenue increased" in answer
    assert sources[0]["file_name"] == "report.pdf"


def test_chunking_splits_long_text():
    text = ("Paragraph one.\n\n" + "Paragraph two has more content. " * 20).strip()
    chunks = split_text_to_chunks(text, chunk_size=120, overlap=20)
    assert len(chunks) >= 2


def test_answer_generator_uses_azure_openai(monkeypatch):
    from app.core import config
    import app.rag.answer_generator as answer_module

    calls = {}

    class FakeMessage:
        content = "The revenue in 2024 Q1 was USD 12.0 million."

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletions:
        def create(self, **kwargs):
            calls.update(kwargs)
            return type("Response", (), {"choices": [FakeChoice()]})()

    class FakeClient:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(config, "USE_AZURE_OPENAI", True)
    monkeypatch.setattr(config, "AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setattr(config, "AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(config, "AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
    monkeypatch.setattr(config, "AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    monkeypatch.setattr(answer_module, "AzureOpenAI", FakeClient)

    generator = answer_module.AnswerGenerator()
    answer, sources = generator.generate(
        "what was the revenue in 2024 Q1",
        [
            {
                "text": "The revenue in 2024 Q1 was USD 12.0 million.",
                "metadata": {"file_name": "report.pdf", "page_number": 1, "content_type": "text"},
            }
        ],
    )

    assert answer == "The revenue in 2024 Q1 was USD 12.0 million."
    assert calls["model"] == "gpt-4o"
    assert calls["client_kwargs"]["azure_endpoint"] == "https://example.openai.azure.com/"
    assert sources[0]["file_name"] == "report.pdf"


def test_answer_generator_falls_back_when_azure_fails(monkeypatch):
    from app.core import config
    import app.rag.answer_generator as answer_module

    class FailingCompletions:
        def create(self, **kwargs):
            raise RuntimeError("deployment not found")

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": FailingCompletions()})()

    monkeypatch.setattr(config, "USE_AZURE_OPENAI", True)
    monkeypatch.setattr(config, "AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setattr(config, "AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(config, "AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
    monkeypatch.setattr(config, "AZURE_OPENAI_DEPLOYMENT", "wrong-deployment")
    monkeypatch.setattr(answer_module, "AzureOpenAI", FakeClient)

    generator = answer_module.AnswerGenerator()
    answer, _ = generator.generate(
        "what was the revenue in 2024 Q1",
        [{"text": "The revenue in 2024 Q1 was USD 12.0 million.", "metadata": {"file_name": "report.pdf"}}],
    )

    assert answer.startswith("I found relevant information in the uploaded documents")
    assert "USD 12.0 million" in answer


def test_answer_generator_uses_cropped_pdf_visual_url(monkeypatch):
    from app.core import config
    import app.rag.answer_generator as answer_module

    monkeypatch.setattr(config, "USE_AZURE_OPENAI", False)

    generator = answer_module.AnswerGenerator()
    _, sources = generator.generate(
        "show the revenue chart",
        [
            {
                "text": "The visual chart shows revenue from Q1 to Q4.",
                "metadata": {
                    "file_name": "company_chart.pdf",
                    "page_number": 1,
                    "content_type": "chart_summary",
                    "chunk_type": "chart_summary",
                    "contains_chart": True,
                    "visual_type": "chart",
                },
            }
        ],
    )

    assert sources[0]["visual_url"] == "/visuals/company_chart.pdf?page_number=1&crop=visual"


def test_answer_generator_uses_cropped_raster_visual_url(monkeypatch):
    from app.core import config
    import app.rag.answer_generator as answer_module

    monkeypatch.setattr(config, "USE_AZURE_OPENAI", False)

    generator = answer_module.AnswerGenerator()
    _, sources = generator.generate(
        "what is the first step in cnn architecture?",
        [
            {
                "text": "CNN Architecture Diagram. The input image is the first step.",
                "metadata": {
                    "file_name": "cnn_diagram.png",
                    "content_type": "diagram_summary",
                    "chunk_type": "diagram_summary",
                    "contains_diagram": True,
                    "contains_image": True,
                    "visual_type": "architecture",
                },
            }
        ],
    )

    assert sources[0]["visual_url"] == "/visuals/cnn_diagram.png?crop=visual"


def test_answer_generator_scopes_direct_visual_question_to_top_visual_source(monkeypatch):
    from app.core import config
    import app.rag.answer_generator as answer_module

    monkeypatch.setattr(config, "USE_AZURE_OPENAI", False)

    generator = answer_module.AnswerGenerator()
    answer, sources = generator.generate(
        "what is the first step in cnn architecture?",
        [
            {
                "text": "CNN Architecture Diagram. The input image is the first step, followed by convolution.",
                "score": 50.0,
                "metadata": {
                    "file_name": "cnn_diagram.png",
                    "content_type": "diagram_summary",
                    "chunk_type": "diagram_summary",
                    "contains_diagram": True,
                    "contains_image": True,
                    "visual_type": "architecture",
                    "title": "CNN Architecture Diagram",
                },
            },
            {
                "text": "RNN diagram context that should not be used for the CNN answer.",
                "score": 40.0,
                "metadata": {
                    "file_name": "deep_learning.pdf",
                    "page_number": 7,
                    "content_type": "image_description",
                    "chunk_type": "image_description",
                    "contains_diagram": True,
                    "contains_image": True,
                    "visual_type": "diagram",
                    "title": "Recurrent neural networks",
                },
            },
        ],
    )

    assert "input image" in answer.lower()
    assert "RNN" not in answer
    assert len(sources) == 1
    assert sources[0]["file_name"] == "cnn_diagram.png"


def test_answer_generator_does_not_attach_visual_url_for_generic_pdf_page_image(monkeypatch):
    from app.core import config
    import app.rag.answer_generator as answer_module

    monkeypatch.setattr(config, "USE_AZURE_OPENAI", False)

    generator = answer_module.AnswerGenerator()
    _, sources = generator.generate(
        "what is Expense reimbursement policy",
        [
            {
                "text": "Expense reimbursement policy says claims need receipts.",
                "metadata": {
                    "file_name": "company_policy.pdf",
                    "page_number": 4,
                    "content_type": "image_description",
                    "chunk_type": "image_description",
                    "contains_image": True,
                    "contains_chart": False,
                    "contains_diagram": False,
                    "visual_type": "image",
                },
            }
        ],
    )

    assert sources[0]["visual_url"] is None


def test_answer_generator_prefers_text_source_over_generic_pdf_page_image(monkeypatch):
    from app.core import config
    import app.rag.answer_generator as answer_module

    monkeypatch.setattr(config, "USE_AZURE_OPENAI", False)

    generator = answer_module.AnswerGenerator()
    _, sources = generator.generate(
        "what is Expense reimbursement policy",
        [
            {
                "text": "Expense reimbursement policy says claims need receipts.",
                "score": 10.0,
                "metadata": {
                    "file_name": "company_policy.pdf",
                    "page_number": 4,
                    "content_type": "pdf_text",
                    "chunk_type": "pdf_text",
                },
            },
            {
                "text": "Rendered page OCR with the same policy text.",
                "score": 9.0,
                "metadata": {
                    "file_name": "company_policy.pdf",
                    "page_number": 4,
                    "content_type": "image_description",
                    "chunk_type": "image_description",
                    "contains_image": True,
                    "visual_type": "image",
                },
            },
        ],
    )

    assert len(sources) == 1
    assert sources[0]["content_type"] == "pdf_text"


def test_answer_generator_does_not_attach_pdf_visual_for_nonvisual_text_question(monkeypatch):
    from app.core import config
    import app.rag.answer_generator as answer_module

    monkeypatch.setattr(config, "USE_AZURE_OPENAI", False)

    generator = answer_module.AnswerGenerator()
    _, sources = generator.generate(
        "Types of deep learning",
        [
            {
                "text": "Generative adversarial networks (GANs) create new data resembling the original training data.",
                "score": 12.0,
                "metadata": {
                    "file_name": "deep_learning.pdf",
                    "page_number": 9,
                    "content_type": "pdf_text",
                    "chunk_type": "pdf_text",
                    "contains_diagram": True,
                    "visual_type": "architecture",
                    "title": "Generative adversarial networks (GANs)",
                },
            },
            {
                "text": "Rendered page image for the same deep learning article.",
                "score": 11.0,
                "metadata": {
                    "file_name": "deep_learning.pdf",
                    "page_number": 9,
                    "content_type": "image_description",
                    "chunk_type": "image_description",
                    "contains_diagram": True,
                    "visual_type": "diagram",
                    "title": "Deep Learning",
                },
            },
        ],
    )

    assert len(sources) == 1
    assert sources[0]["content_type"] == "pdf_text"
    assert sources[0]["visual_url"] is None


def test_answer_generator_hides_low_relevance_visual_source_for_text_question(monkeypatch):
    from app.core import config
    import app.rag.answer_generator as answer_module

    monkeypatch.setattr(config, "USE_AZURE_OPENAI", False)

    generator = answer_module.AnswerGenerator()
    answer, sources = generator.generate(
        "what is Machine Learning Workflow",
        [
            {
                "text": "Machine Learning Workflow\nData Collection: Gathering raw data.",
                "score": 12.0,
                "metadata": {
                    "file_name": "machine_learning.txt",
                    "content_type": "text",
                    "chunk_type": "text",
                    "title": "Machine Learning Workflow",
                    "visual_type": "architecture",
                },
            },
            {
                "text": "A loosely related visual says Machine Learning is inside Artificial Intelligence.",
                "score": 2.0,
                "metadata": {
                    "file_name": "genai.pdf",
                    "page_number": 1,
                    "content_type": "diagram_summary",
                    "chunk_type": "diagram_summary",
                    "contains_diagram": True,
                    "visual_type": "taxonomy",
                },
            },
        ],
    )

    assert "Data Collection" in answer
    assert len(sources) == 1
    assert sources[0]["file_name"] == "machine_learning.txt"
    assert sources[0]["visual_type"] is None
    assert sources[0]["visual_url"] is None


def test_vector_store_uses_persistent_local_fallback_when_qdrant_unavailable(tmp_path, monkeypatch):
    from app.core import config
    import app.vectorstores.qdrant_store as store_module

    monkeypatch.setattr(config, "VECTOR_STORE", "qdrant")
    monkeypatch.setattr(config, "QDRANT_LOCAL_PATH", tmp_path / "vectors")
    monkeypatch.setattr(store_module, "QdrantClient", None)
    monkeypatch.setattr(store_module, "rest", None)
    monkeypatch.setattr(store_module, "SentenceTransformer", None)

    store = store_module.QdrantStore()
    stored = store.upsert_documents(
        [
            {
                "id": "1",
                "text": "local fallback document",
                "metadata": {"file_name": "a.txt", "source_file": "a.txt", "content_type": "text"},
            }
        ]
    )

    reloaded = store_module.QdrantStore()
    results = reloaded.search("local fallback", top_k=1)

    assert store.vector_store_name == "local"
    assert stored == 1
    assert results[0]["text"] == "local fallback document"
