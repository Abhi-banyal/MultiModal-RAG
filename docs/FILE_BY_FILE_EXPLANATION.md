
1. app/main.py

2. app/core/config.py
3. app/core/logging.py

4. app/api/schemas.py
5. app/api/routes.py

6. app/rag/query_parser.py
7. app/rag/retriever.py
8. app/vectorstores/qdrant_store.py
9. app/rag/reranker.py
10. app/rag/prompts.py
11. app/rag/answer_generator.py
12. app/rag/graph.py

13. app/ingestion/loaders.py
14. app/ingestion/docling_extractor.py
15. app/ingestion/image_ocr.py
16. app/ingestion/vision_processor.py
17. app/ingestion/visual_analyzer.py
18. app/ingestion/metadata_extractor.py
19. app/ingestion/metadata.py
20. app/ingestion/chunker.py
21. app/ingestion/ingestion_service.py

22. app/utils/
23. data/
24. vectorstores/


# File By File Explanation

This guide explains each important file in the project.

## Root Files And Folders

File: `README.md`

- Purpose: Quick setup and usage guide.
- Important content: install dependencies, run FastAPI, run ingestion, verify vectors.
- Used by: humans.
- Runs when: never directly.
- Workflow role: project instructions.

File: `requirements.txt`

- Purpose: Python dependency list.
- Important packages: `fastapi`, `uvicorn`, `pydantic`, `qdrant-client`, `pymupdf`, `pdfplumber`, `pillow`, `pytesseract`, `sentence-transformers`, `openai`, `langgraph`, `pytest`.
- Used by: `pip install -r requirements.txt`.
- Workflow role: environment setup.

Folder: `data/`

- Purpose: Source documents for ingestion.
- Current examples: `genai.pdf`, `deep_learning.pdf`, `company_report.pdf`, `company_chart.pdf`, `company_policy.pdf`, `cnn_diagram.png`, `machine_learning.txt`.
- Used by: `app/ingestion/loaders.py`.
- Workflow role: input files.

Folder: `vectorstores/`

- Purpose: Local Qdrant persistent storage.
- Used by: `QdrantStore`.
- Workflow role: vector database files.

File: `.index_meta.json`

- Purpose: Tracks which files were indexed, hashes, chunk counts, embedding model.
- Used by: `IngestionService`.
- Workflow role: prevents unnecessary re-ingestion.

Folder: `tests/`

- Purpose: Test suite.
- Used by: `pytest`.
- Workflow role: verification.

Folder: `scripts/`

- Purpose: Manual validation scripts.
- Important file: `scripts/test_rag_pipeline.py`.

## App Entry

File: `app/main.py`

- Purpose: Creates the FastAPI application.
- Important functions/classes:
  - `lifespan`
  - `app = FastAPI(...)`
  - `root`
- Used by: Uvicorn command `python -m uvicorn app.main:app --reload`.
- Runs when: backend starts.
- Workflow role: API server entry point.

Important syntax:

```python
app = FastAPI(title="Multimodal RAG Chatbot", lifespan=lifespan)
app.include_router(routes.router)
```

This creates the backend app and attaches routes from `app/api/routes.py`.

## API Layer

File: `app/api/routes.py`

- Purpose: Defines API endpoints.
- Important functions:
  - `get_rag_graph`
  - `health`
  - `ingest`
  - `chat`
  - `debug_search`
  - `debug_chunks`
  - `list_documents`
  - `delete_index`
- Used by: `app/main.py`.
- Runs when: API requests arrive.
- Workflow role: API routing.

File: `app/api/schemas.py`

- Purpose: Defines request and response models.
- Important classes:
  - `HealthResponse`
  - `IngestRequest`
  - `IngestResponse`
  - `ChatRequest`
  - `ChatResponse`
  - `Source`
  - `DebugSearchRequest`
  - `DebugChunksRequest`
  - `DocumentMeta`
- Used by: `routes.py`.
- Runs when: FastAPI validates requests/responses.
- Workflow role: API data contracts.

## Core Layer

File: `app/core/config.py`

- Purpose: Loads settings from `.env`.
- Important classes/functions:
  - `Settings(BaseSettings)`
  - `resolved_data_dir`
  - `resolved_index_metadata_path`
  - `resolved_qdrant_local_path`
- Used by: almost every module.
- Runs when: imported.
- Workflow role: configuration.

File: `app/core/logging.py`

- Purpose: Creates shared logger.
- Important functions/objects:
  - `setup_logging`
  - `logger`
- Used by: ingestion, vector store, RAG, API modules.
- Workflow role: logging.

## Ingestion Layer

File: `app/ingestion/loaders.py`

- Purpose: Finds and loads simple files.
- Important functions:
  - `list_data_files`
  - `load_txt`
  - `load_csv_as_markdown`
- Used by: `IngestionService`.
- Workflow role: file discovery and basic loading.

File: `app/ingestion/docling_extractor.py`

- Purpose: Extracts PDF page text, tables, embedded images, and rendered page images.
- Important functions:
  - `_extract_tables_with_pdfplumber`
  - `_extract_images_with_pymupdf`
  - `_render_page_image`
  - `extract_pdf`
- Used by: `IngestionService._ingest_pdf_file`.
- Workflow role: PDF extraction.

File: `app/ingestion/image_ocr.py`

- Purpose: Runs Tesseract OCR on images.
- Important function:
  - `ocr_image`
- Used by: `vision_processor.py`.
- Workflow role: OCR.

File: `app/ingestion/vision_processor.py`

- Purpose: Combines Tesseract OCR with optional OpenAI/Azure vision description.
- Important classes/functions:
  - `VisionProcessingResult`
  - `_describe_with_vision_model`
  - `process_image`
  - `describe_image`
- Used by: `IngestionService`.
- Workflow role: image text extraction and vision enrichment.

File: `app/ingestion/visual_analyzer.py`

- Purpose: Creates self-contained visual summaries.
- Important functions:
  - `genai_taxonomy_summary`
  - `cnn_architecture_summary`
  - `generic_visual_description`
  - `visual_summaries_for_content`
- Used by: `IngestionService`.
- Workflow role: multimodal summarization.

File: `app/ingestion/metadata.py`

- Purpose: Creates base file metadata.
- Important function:
  - `file_meta`
- Used by: `IngestionService._meta_for`.
- Workflow role: document metadata.

File: `app/ingestion/metadata_extractor.py`

- Purpose: Extracts semantic metadata from text.
- Important functions:
  - `extract_year`
  - `extract_quarters`
  - `extract_metrics`
  - `infer_document_type`
  - `infer_visual_type`
  - `enrich_metadata_for_text`
  - `structured_chart_summary`
- Used by: `chunker.py`, `ingestion_service.py`, `answer_generator.py`, `query_parser.py`.
- Workflow role: metadata enrichment.

File: `app/ingestion/chunker.py`

- Purpose: Splits text into chunks and creates chunk documents.
- Important functions:
  - `split_text_to_chunks`
  - `detect_section_title`
  - `format_chunk_text`
  - `create_chunk_docs`
- Used by: `IngestionService`.
- Workflow role: chunk creation.

File: `app/ingestion/ingestion_service.py`

- Purpose: Main ingestion orchestrator.
- Important class:
  - `IngestionService`
- Important methods:
  - `_ingest_text_file`
  - `_ingest_csv_file`
  - `_ingest_image_file`
  - `_ingest_pdf_file`
  - `_ingest_file`
  - `ingest_all`
- Used by: `POST /ingest`, terminal ingestion command, `scripts/test_rag_pipeline.py`.
- Workflow role: vector generation.

## Vector Store Layer

File: `app/vectorstores/qdrant_store.py`

- Purpose: Embeds text and stores/searches vectors.
- Important class:
  - `QdrantStore`
- Important methods:
  - `_load_embedding_model`
  - `_connect_vector_store`
  - `_embed_texts`
  - `upsert_documents`
  - `search`
  - `count_vectors`
  - `delete_file_vectors`
  - `list_chunks`
  - `clear_collection`
- Used by: ingestion, retrieval, debug endpoints.
- Workflow role: vector database abstraction.

## RAG Layer

File: `app/rag/query_parser.py`

- Purpose: Parses user questions.
- Important functions:
  - `parse_query_filters`
  - `metadata_matches_filter`
  - `metadata_priority_score`
- Used by: retriever, reranker, graph, answer generator.
- Workflow role: query understanding.

File: `app/rag/retriever.py`

- Purpose: Retrieves candidate chunks from Qdrant.
- Important class:
  - `Retriever`
- Important methods:
  - `_tokens`
  - `_keyword_score`
  - `_merge_debug_scores`
  - `retrieve`
- Used by: `RAGGraph`.
- Workflow role: first-stage retrieval.

File: `app/rag/reranker.py`

- Purpose: Reranks retrieved chunks.
- Important class:
  - `Reranker`
- Important method:
  - `rerank`
- Used by: `RAGGraph`.
- Workflow role: second-stage ranking.

File: `app/rag/prompts.py`

- Purpose: Builds the final LLM prompt.
- Important objects/functions:
  - `PROMPT_TEMPLATE`
  - `build_prompt`
- Used by: `AnswerGenerator`.
- Workflow role: prompt construction.

File: `app/rag/answer_generator.py`

- Purpose: Calls Azure OpenAI or returns extractive fallback answer.
- Important class:
  - `AnswerGenerator`
- Important methods:
  - `_configure_azure_openai`
  - `_configure_openai_answer`
  - `_extractive_answer`
  - `_build_sources`
  - `_call_answer_model`
  - `generate`
- Used by: `RAGGraph`.
- Workflow role: final answer generation.

File: `app/rag/graph.py`

- Purpose: Orchestrates the full RAG workflow.
- Important classes:
  - `RAGState`
  - `RAGGraph`
- Important methods:
  - `_receive_question`
  - `_rewrite_query`
  - `_retrieve_context`
  - `_rerank_context`
  - `_maybe_ask_clarification`
  - `_build_context_chunks`
  - `_generate_answer`
  - `_validate_answer`
  - `run`
  - `debug_search`
- Used by: `POST /chat`, `POST /debug/search`.
- Workflow role: RAG pipeline controller.

## Utility Layer

File: `app/utils/file_hash.py`

- Purpose: Creates SHA-256 hash for each file.
- Important function:
  - `file_hash`
- Used by: metadata and ingestion.
- Workflow role: detect changed files.

File: `app/utils/text_cleaning.py`

- Purpose: Basic whitespace cleanup.
- Important function:
  - `clean_text`
- Used by: currently available as utility; not central to current pipeline.
- Workflow role: utility.

## Tests And Scripts

File: `scripts/test_rag_pipeline.py`

- Purpose: Manual end-to-end validation.
- Workflow role: smoke test.

File: `tests/test_api.py`

- Purpose: Tests FastAPI routes.

File: `tests/test_ingestion.py`

- Purpose: Tests chunking, file hashing, ingestion behavior, OCR fallback.

File: `tests/test_rag.py`

- Purpose: Tests metadata, query parsing, retrieval filters, visual ranking, graph behavior, Azure fallback, local vector fallback.
