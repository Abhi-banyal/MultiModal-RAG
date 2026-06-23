# API Workflow

This document explains every API endpoint in the backend.

## How APIs Are Registered

File: `app/main.py`

```python
app = FastAPI(title="Multimodal RAG Chatbot", lifespan=lifespan)
app.include_router(routes.router)
```

Routes are defined in:

```text
app/api/routes.py
```

Data models are defined in:

```text
app/api/schemas.py
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## Endpoint: `GET /`

Method: `GET`

File:

```text
app/main.py
```

Handler:

```python
@app.get("/")
def root():
    return {
        "message": "Multimodal RAG backend is running",
        "docs": "http://127.0.0.1:8000/docs"
    }
```

Purpose:

- Basic check that backend is running.

Request body:

```text
None
```

Example:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/" -Method Get
```

Example response:

```json
{
  "message": "Multimodal RAG backend is running",
  "docs": "http://127.0.0.1:8000/docs"
}
```

Internal workflow:

```text
HTTP request -> root() -> static JSON response
```

## Endpoint: `GET /docs`

Method: `GET`

File:

```text
Provided automatically by FastAPI
```

Purpose:

- Opens Swagger UI.
- Lets you test `POST /chat`, `POST /ingest`, and debug endpoints from browser.

URL:

```text
http://127.0.0.1:8000/docs
```

Internal workflow:

```text
FastAPI reads route definitions -> generates OpenAPI schema -> renders Swagger UI
```

## Endpoint: `GET /health`

Method: `GET`

File:

```text
app/api/routes.py
```

Handler:

```python
@router.get("/health", response_model=schemas.HealthResponse)
def health():
    store = QdrantStore()
    return {
        "status": "ok",
        "vector_store": store.vector_store_name,
        "collection": config.QDRANT_COLLECTION,
        "embedding_model": config.EMBEDDING_MODEL,
        "vector_count": store.count_vectors(),
    }
```

Purpose:

- Checks backend and vector database status.

Request body:

```text
None
```

Example:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
```

Example response:

```json
{
  "status": "ok",
  "vector_store": "local",
  "collection": "multimodal_rag",
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "vector_count": 755
}
```

Internal workflow:

```text
/health
  -> QdrantStore()
  -> load embedding model
  -> connect local/remote Qdrant
  -> count_vectors()
  -> return status JSON
```

Possible errors:

- Embedding model cannot load.
- Qdrant local path is locked or corrupted.
- Remote Qdrant is unavailable.

## Endpoint: `POST /ingest`

Method: `POST`

File:

```text
app/api/routes.py
```

Handler:

```python
@router.post("/ingest", response_model=schemas.IngestResponse)
def ingest(req: schemas.IngestRequest = Body(default_factory=schemas.IngestRequest)):
```

Request model:

```python
class IngestRequest(BaseModel):
    force: bool = False
    reset: bool = False
```

Request body:

```json
{
  "reset": true,
  "force": true
}
```

Meaning:

- `reset=true`: clear vector collection before indexing.
- `force=true`: reprocess files even if unchanged.

Example:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/ingest" -Method Post -ContentType "application/json" -Body '{"reset":true,"force":true}'
```

Example response:

```json
{
  "status": "completed_with_warnings",
  "vector_store": "qdrant_local",
  "collection": "multimodal_rag",
  "total_files": 7,
  "processed_files": ["cnn_diagram.png", "company_chart.pdf"],
  "failed_files": [],
  "skipped_files": [],
  "total_chunks_created": 760,
  "vectors_stored": 760,
  "vector_store_count_after_ingest": 755,
  "warnings": [],
  "errors": []
}
```

Internal workflow:

```text
/ingest
  -> IngestionService()
      -> QdrantStore()
  -> ingest_all(force=req.force, reset=req.reset)
      -> list_data_files()
      -> _ingest_file()
      -> create_chunk_docs()
      -> QdrantStore.upsert_documents()
  -> get_rag_graph.cache_clear()
  -> return ingestion summary
```

Why `cache_clear()` matters:

```python
get_rag_graph.cache_clear()
```

`get_rag_graph` is cached with `@lru_cache`. After ingestion, clearing cache forces future chat requests to use fresh vector state.

Possible errors:

- Broken PDF.
- Missing Tesseract.
- Embedding model unavailable.
- Qdrant path locked.
- All files fail, endpoint returns HTTP 500.

## Endpoint: `POST /chat`

Method: `POST`

File:

```text
app/api/routes.py
```

Handler:

```python
@router.post("/chat", response_model=schemas.ChatResponse)
def chat(req: schemas.ChatRequest):
    answer, sources = get_rag_graph().run(req.question)
```

Request model:

```python
class ChatRequest(BaseModel):
    question: str
```

Request body:

```json
{
  "question": "What is taxonomy of GenAI-related disciplines?"
}
```

Response model:

```python
class ChatResponse(BaseModel):
    answer: str
    sources: List[Source] = Field(default_factory=list)
```

Example response:

```json
{
  "answer": "The taxonomy is a nested hierarchy: Artificial Intelligence contains Machine Learning, Machine Learning contains Deep Learning, and Deep Learning contains Generative AI...",
  "sources": [
    {
      "file_name": "genai.pdf",
      "page_number": 1,
      "content_type": "diagram_summary",
      "chunk_type": "diagram_summary",
      "title": "A taxonomy of GenAI-related disciplines",
      "caption": "Figure 1: A taxonomy of GenAI-related disciplines.",
      "figure_number": "1",
      "visual_type": "taxonomy",
      "year": 2022,
      "score": 18.96,
      "rerank_score": 8.29,
      "matched_text_preview": "Document: genai.pdf Page: 1 Chunk type: diagram_summary..."
    }
  ]
}
```

Internal workflow:

```text
/chat
  -> get_rag_graph()
      -> RAGGraph()
  -> RAGGraph.run(question)
      -> parse_query_filters()
      -> Retriever.retrieve()
      -> QdrantStore.search()
      -> Reranker.rerank()
      -> build context chunks
      -> AnswerGenerator.generate()
      -> build_prompt()
      -> Azure OpenAI chat completion
  -> answer + sources
```

Possible errors:

- No vectors exist.
- Azure OpenAI settings missing.
- Azure deployment name wrong.
- Query retrieves irrelevant context.
- Reranker model cannot load.

Fallback behavior:

- If Azure OpenAI is unavailable, answer generator returns an extractive answer from retrieved chunks.
- If nothing is retrieved, `/chat` returns:

```text
I could not find this information in the uploaded documents.
```

## Endpoint: `POST /debug/search`

Method: `POST`

File:

```text
app/api/routes.py
```

Handler:

```python
@router.post("/debug/search")
def debug_search(req: schemas.DebugSearchRequest):
    ranked = get_rag_graph().debug_search(req.question)
```

Request model:

```python
class DebugSearchRequest(BaseModel):
    question: str
```

Request body:

```json
{
  "question": "What was the revenue in Q4 2024?"
}
```s

Purpose:

- Shows which chunks retrieval/reranking selected.
- Best endpoint for debugging wrong answers.

Example response fields:

```json
{
  "question": "What was the revenue in Q4 2024?",
  "chunks": [
    {
      "file_name": "company_chart.pdf",
      "page_number": 1,
      "content_type": "chart_summary",
      "chunk_type": "chart_summary",
      "year": 2024,
      "quarter": ["Q1", "Q2", "Q3", "Q4"],
      "metric_names": ["revenue", "net_profit"],
      "score": 23.33,
      "rerank_score": 5.09,
      "text_preview": "Document: company_chart.pdf..."
    }
  ]
}
```

Internal workflow:

```text
/debug/search
  -> RAGGraph.debug_search()
      -> Retriever.retrieve()
      -> Reranker.rerank()
  -> return chunk metadata and previews
```

## Endpoint: `POST /debug/chunks`

Method: `POST`

File:

```text
app/api/routes.py
```

Handler:

```python
@router.post("/debug/chunks")
def debug_chunks(req: schemas.DebugChunksRequest):
    store = QdrantStore()
    for item in store.list_chunks(file_name=req.file_name, limit=500):
```

Request model:

```python
class DebugChunksRequest(BaseModel):
    file_name: str
```

Request body:

```json
{
  "file_name": "genai.pdf"
}
```

Purpose:

- Lists stored chunks for one file.
- Useful after ingestion.

Internal workflow:

```text
/debug/chunks
  -> QdrantStore()
  -> list_chunks(file_name)
  -> return metadata + text preview
```

Use it to confirm:

- `diagram_summary` exists.
- `chart_summary` exists.
- `page_ocr` exists.
- metadata fields are correct.

## Endpoint: `GET /documents`

Method: `GET`

File:

```text
app/api/routes.py
```

Handler:

```python
@router.get("/documents", response_model=List[schemas.DocumentMeta])
def list_documents():
```

Purpose:

- Reads `.index_meta.json`.
- Returns indexed document metadata.

Example:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/documents" -Method Get
```

Response:

```json
[
  {
    "file_name": "genai.pdf",
    "file_path": "D:\\multimodal_rag\\data\\genai.pdf",
    "file_type": "pdf",
    "last_indexed": "2026-06-15T..."
  }
]
```

## Endpoint: `DELETE /index`

Method: `DELETE`

File:

```text
app/api/routes.py
```

Handler:

```python
@router.delete("/index")
def delete_index():
    store = QdrantStore()
    store.clear_collection()
    if config.INDEX_METADATA_PATH.exists():
        config.INDEX_METADATA_PATH.unlink()
    return {"status": "ok"}
```

Purpose:

- Clears vector store collection.
- Deletes `.index_meta.json`.

Example:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/index" -Method Delete
```

Internal workflow:

```text
/index DELETE
  -> QdrantStore.clear_collection()
  -> delete .index_meta.json
  -> return {"status": "ok"}
```

Warning:

- After this, `/chat` will not work well until you run ingestion again.

## Upload API

This project currently has no upload endpoint.

Current workflow:

1. Put files manually into `data/`.
2. Run `POST /ingest`.
3. Ask questions with `POST /chat`.

Possible future endpoint:

```text
POST /upload
```

It would save uploaded files to `data/` and optionally trigger ingestion.

## API Workflow Summary

```text
GET /
  -> backend status

GET /health
  -> vector count and config status

POST /ingest
  -> generate vectors from data/

POST /chat
  -> answer question from indexed chunks

POST /debug/search
  -> inspect retrieved/reranked chunks

POST /debug/chunks
  -> inspect stored chunks for one file

GET /documents
  -> list indexed files

DELETE /index
  -> clear vector index
```
