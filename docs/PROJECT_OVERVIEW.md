# Project Overview

This document explains the application from beginner to advanced level. It uses the actual files and function names in this repository.

## What This Application Does

This project is a FastAPI backend for a multimodal RAG chatbot.

RAG means Retrieval Augmented Generation:

1. Store useful document content in a searchable vector database.
2. When the user asks a question, retrieve the most relevant chunks.
3. Send those chunks to an LLM.
4. Return an answer grounded in the uploaded files.

This app reads files from `data/`, extracts text and visual content, creates embeddings, stores vectors in Qdrant, and answers questions through APIs.

## Normal RAG vs Multimodal RAG

Normal RAG usually handles only text:

`PDF text -> chunks -> embeddings -> vector search -> LLM answer`

This app is multimodal because it also handles images and visual content:

`PDF page image -> OCR/vision -> diagram_summary/chart_summary -> embeddings -> vector search -> LLM answer`

Supported content includes:

- PDF selectable text
- PDF tables
- Rendered PDF page OCR
- Embedded PDF images
- Standalone `.png`, `.jpg`, `.jpeg`
- Diagrams
- Charts
- OCR text
- Visual summaries

## Main Purpose

The purpose is to let users ask questions about mixed document types, including text-heavy PDFs and visual files. Example questions:

- `What does the policy say about passwords?`
- `What was the revenue in Q4 2024?`
- `What is taxonomy of GenAI-related disciplines?`
- `Explain the CNN architecture diagram.`

## High-Level Architecture

```text
data/
  PDFs, images, text files
        |
        v
app/ingestion/
  extract text, OCR, visual summaries, chunks, metadata
        |
        v
app/vectorstores/qdrant_store.py
  embeddings + Qdrant/local vector storage
        |
        v
app/rag/
  query parsing -> retrieval -> reranking -> prompt -> answer
        |
        v
app/api/routes.py
  FastAPI endpoints return JSON responses
```

## Ingestion Time vs Query Time

Ingestion time happens before asking questions. It prepares the database.

```text
data files -> extraction -> OCR/vision -> chunks -> embeddings -> Qdrant vectors
```

Main entry points:

- `POST /ingest`
- Direct terminal command:

```powershell
.\venv\Scripts\python.exe -c "from app.ingestion.ingestion_service import IngestionService; print(IngestionService().ingest_all(force=True, reset=True))"
```

Query time happens when a user asks a question.

```text
user question -> API -> query parsing -> query embedding -> Qdrant search -> reranker -> context -> Azure OpenAI -> answer + sources
```

Main entry point:

- `POST /chat`

## Important Runtime Objects

- `FastAPI` app: created in `app/main.py`.
- `APIRouter`: created in `app/api/routes.py`.
- `IngestionService`: manages vector generation.
- `QdrantStore`: manages embeddings and vector database operations.
- `Retriever`: performs dense search plus metadata/keyword scoring.
- `Reranker`: reranks candidate chunks with a CrossEncoder.
- `RAGGraph`: orchestrates the answer workflow.
- `AnswerGenerator`: calls Azure OpenAI or falls back to extractive answers.

## Beginner Mental Model

Think of the app as two machines.

Machine 1: index builder

```text
Reads files -> turns every useful part into text -> converts text into vectors -> stores vectors
```

Machine 2: question answerer

```text
Reads question -> finds matching vectors -> sends matching text to LLM -> returns answer
```

## Advanced Mental Model

The app does more than basic vector search.

- It adds metadata such as `year`, `quarter`, `chunk_type`, `figure_number`, and `contains_diagram`.
- It parses user questions before retrieval.
- It applies hard filters for exact year/file/page/figure when available.
- It boosts visual chunks when the user asks visual questions.
- It reranks candidates after retrieval.
- It builds prompts that instruct the LLM to answer only from retrieved context.

## Learning Path

Step 1: Learn Python syntax used in this project

- Study: `app/ingestion/ingestion_service.py`, `app/vectorstores/qdrant_store.py`
- Learn: imports, classes, functions, dictionaries, lists, `try/except`
- Practice: print all files returned by `list_data_files()`
- Expected output: file paths from `data/`

Step 2: Learn FastAPI

- Study: `app/main.py`, `app/api/routes.py`
- Learn: `FastAPI()`, `APIRouter()`, route decorators
- Practice: add a temporary `GET /hello` endpoint
- Expected output: JSON like `{"message": "hello"}`

Step 3: Learn Pydantic

- Study: `app/api/schemas.py`, `app/core/config.py`
- Learn: `BaseModel`, `Field`, `BaseSettings`
- Practice: add a field to `ChatRequest`
- Expected output: Swagger shows the new field

Step 4: Learn PDF/image extraction

- Study: `app/ingestion/docling_extractor.py`, `app/ingestion/image_ocr.py`
- Learn: PyMuPDF, pdfplumber, Pillow, Tesseract
- Practice: print text from page 1 of `genai.pdf`
- Expected output: page text and OCR text

Step 5: Learn embeddings

- Study: `QdrantStore._embed_texts`
- Learn: how text becomes numeric vectors
- Practice: embed two short strings and print vector length
- Expected output: length `384` for MiniLM embeddings

Step 6: Learn Qdrant

- Study: `upsert_documents`, `search`, `list_chunks`
- Learn: collections, points, payloads, filters
- Practice: run `QdrantStore().count_vectors()`
- Expected output: number greater than `0`

Step 7: Learn retrieval

- Study: `app/rag/retriever.py`
- Learn: query parsing, dense search, keyword score, metadata score
- Practice: call `RAGGraph().debug_search("What was the revenue in Q4 2024?")`
- Expected output: top chunk from `company_chart.pdf`

Step 8: Learn reranking

- Study: `app/rag/reranker.py`
- Learn: CrossEncoder reranking
- Practice: temporarily set `USE_RERANKER=false`
- Expected output: answers still work, but ranking may be weaker

Step 9: Learn Azure OpenAI answer generation

- Study: `app/rag/answer_generator.py`
- Learn: client setup, chat completions, fallback behavior
- Practice: ask `POST /chat`
- Expected output: answer plus sources

Step 10: Learn complete RAG pipeline

- Study: `app/rag/graph.py`
- Learn: the end-to-end graph
- Practice: trace every state field: `question`, `query`, `candidates`, `ranked`, `context_chunks`
- Expected output: clear understanding of each step

Step 11: Learn multimodal improvements

- Study: `app/ingestion/visual_analyzer.py`, `app/rag/query_parser.py`
- Learn: visual summaries and visual-aware ranking
- Practice: ask `What is taxonomy of GenAI-related disciplines?`
- Expected output: answer from `genai.pdf`, page 1, `diagram_summary`

## 7-Day Study Plan

Day 1: Run the app and understand folder structure.

- Read `README.md`, `docs/PROJECT_OVERVIEW.md`, `app/main.py`
- Run `GET /health`

Day 2: Study ingestion.

- Read `app/ingestion/ingestion_service.py`
- Run ingestion with `force=True, reset=True`

Day 3: Study chunking and metadata.

- Read `app/ingestion/chunker.py`, `metadata.py`, `metadata_extractor.py`
- Inspect chunks using `POST /debug/chunks`

Day 4: Study Qdrant and embeddings.

- Read `app/vectorstores/qdrant_store.py`
- Run vector count and search commands

Day 5: Study retrieval and reranking.

- Read `app/rag/query_parser.py`, `retriever.py`, `reranker.py`
- Use `POST /debug/search`

Day 6: Study answer generation and prompts.

- Read `app/rag/answer_generator.py`, `prompts.py`, `graph.py`
- Ask text and visual questions

Day 7: Debug and improve.

- Read `docs/DEBUGGING_GUIDE.md`
- Turn on `DEBUG_RETRIEVAL_SCORES=true`
- Try one improvement, then run `pytest`
