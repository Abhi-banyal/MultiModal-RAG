# Commands And Environment Variables

All commands here are for Windows PowerShell from the project root:

```powershell
cd D:\multimodal_rag
```

## Virtual Environment

Activate:

```powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Use Python directly without activation:

```powershell
.\venv\Scripts\python.exe --version
```

## Install Requirements

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

If no venv exists:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run Backend

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Run Frontend

There is no frontend in this repository.

Use Swagger:

```text
http://127.0.0.1:8000/docs
```

## Check Backend

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/" -Method Get
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
```

## Run Ingestion

API:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/ingest" -Method Post -ContentType "application/json" -Body '{"reset":true,"force":true}'
```

Direct terminal:

```powershell
.\venv\Scripts\python.exe -c "from app.ingestion.ingestion_service import IngestionService; print(IngestionService().ingest_all(force=True, reset=True))"
```

## Delete Vectorstore

Stop backend first if it is running.

```powershell
Remove-Item -LiteralPath ".\vectorstores\qdrant_local" -Recurse -Force
Remove-Item -LiteralPath ".\.index_meta.json" -Force
```

Then regenerate:

```powershell
.\venv\Scripts\python.exe -c "from app.ingestion.ingestion_service import IngestionService; print(IngestionService().ingest_all(force=True, reset=True))"
```

## Delete Index Through API

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/index" -Method Delete
```

## Check Vector Count

```powershell
.\venv\Scripts\python.exe -c "from app.vectorstores.qdrant_store import QdrantStore; print(QdrantStore().count_vectors())"
```

## Debug Search

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/debug/search" -Method Post -ContentType "application/json" -Body '{"question":"What is taxonomy of GenAI-related disciplines?"}'
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/debug/search" -Method Post -ContentType "application/json" -Body '{"question":"What was the revenue in Q4 2024?"}'
```

## Inspect Chunks

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/debug/chunks" -Method Post -ContentType "application/json" -Body '{"file_name":"genai.pdf"}'
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/debug/chunks" -Method Post -ContentType "application/json" -Body '{"file_name":"company_chart.pdf"}'
```

## Ask Chat Questions

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/chat" -Method Post -ContentType "application/json" -Body '{"question":"What is taxonomy of GenAI-related disciplines?"}'
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/chat" -Method Post -ContentType "application/json" -Body '{"question":"Explain the CNN architecture diagram."}'
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/chat" -Method Post -ContentType "application/json" -Body '{"question":"What was the revenue in Q4 2024?"}'
```

## Run Tests

```powershell
.\venv\Scripts\python.exe -m pytest
```

Run one file:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_rag.py
```

Run matching tests:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_rag.py -k visual
```

## Run Manual RAG Validation

```powershell
.\venv\Scripts\python.exe scripts\test_rag_pipeline.py
```

## Run Local Qdrant With Docker

Only needed if you want remote Qdrant instead of embedded local Qdrant.

```powershell
docker run -p 6333:6333 -p 6334:6334 -v ${PWD}/qdrant_storage:/qdrant/storage qdrant/qdrant
```

Then set:

```env
VECTOR_STORE=qdrant
QDRANT_URL=http://localhost:6333
```

## Git Commands

Check status:

```powershell
git status
```

Add files:

```powershell
git add .
```

Commit:

```powershell
git commit -m "Add multimodal RAG learning documentation"
```

Push:

```powershell
git push origin main
```

Note: this folder was not a Git repository when checked earlier. If needed, initialize Git:

```powershell
git init
git branch -M main
```

## Environment Variables

Environment variables are read by `app/core/config.py`.

File:

```text
.env
```

Example template:

```text
.env.example
```

Do not commit real secrets.

### DATA_DIR

Purpose: folder containing source documents.

Used by: `app/ingestion/loaders.py`.

Required: optional, default `./data`.

Example:

```env
DATA_DIR=./data
```

### INDEX_METADATA_PATH

Purpose: stores file hash/index metadata.

Used by: `IngestionService`.

Required: optional.

Example:

```env
INDEX_METADATA_PATH=./.index_meta.json
```

### AZURE_OPENAI_ENDPOINT

Purpose: Azure OpenAI endpoint URL.

Used by: `AnswerGenerator`, optional vision analysis.

Required: required if `USE_AZURE_OPENAI=true`.

Example:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
```

If missing:

```text
Azure OpenAI is enabled but endpoint/key/version/deployment is missing.
```

### AZURE_OPENAI_API_KEY

Purpose: Azure OpenAI secret key.

Used by: OpenAI SDK.

Required: required if `USE_AZURE_OPENAI=true`.

Example:

```env
AZURE_OPENAI_API_KEY=your-key-here
```

Never paste real keys into docs or Git.

### AZURE_OPENAI_API_VERSION

Purpose: Azure OpenAI API version.

Used by: OpenAI SDK.

Example:

```env
AZURE_OPENAI_API_VERSION=2025-01-01-preview
```

### AZURE_OPENAI_DEPLOYMENT

Purpose: Azure deployment name for chat completion.

Used by: `AnswerGenerator._call_answer_model`.

Example:

```env
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

If wrong:

- Azure call fails.
- App falls back to extractive answer.

### USE_AZURE_OPENAI

Purpose: choose Azure OpenAI answer generation.

Example:

```env
USE_AZURE_OPENAI=true
```

### USE_OPENAI_VISION

Purpose: optionally call Azure OpenAI vision-capable chat completion during ingestion.

Default:

```env
USE_OPENAI_VISION=false
```

If false, ingestion uses Tesseract OCR and deterministic/local visual summaries only. If true, the app still uses `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_DEPLOYMENT`; there is no separate standard OpenAI API key.

### VECTOR_STORE

Purpose: choose vector store mode.

Values:

```env
VECTOR_STORE=local
```

or

```env
VECTOR_STORE=qdrant
```

`local` uses embedded local Qdrant at `QDRANT_LOCAL_PATH`.

### QDRANT_URL

Purpose: remote Qdrant URL.

Example:

```env
QDRANT_URL=http://localhost:6333
```

### QDRANT_API_KEY

Purpose: API key for secured remote Qdrant.

Optional for local/unauthenticated Qdrant.

### QDRANT_COLLECTION

Purpose: collection name.

Example:

```env
QDRANT_COLLECTION=multimodal_rag
```

### QDRANT_LOCAL_PATH

Purpose: local Qdrant persistence path.

Example:

```env
QDRANT_LOCAL_PATH=./vectorstores/qdrant_local
```

### RESET_VECTOR_STORE

Purpose: clear collection automatically when store initializes.

Normally keep false:

```env
RESET_VECTOR_STORE=false
```

Use true only when intentionally rebuilding.

### FORCE_REINGEST

Purpose: force reprocessing unchanged files.

Example:

```env
FORCE_REINGEST=false
```

### INGEST_SKIP_UNCHANGED

Purpose: skip unchanged files if vectors already exist.

Example:

```env
INGEST_SKIP_UNCHANGED=true
```

### EMBEDDING_MODEL

Purpose: local embedding model.

Example:

```env
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### EMBEDDING_DEVICE

Purpose: CPU/GPU choice for embeddings and reranker.

Example:

```env
EMBEDDING_DEVICE=cpu
```

### NORMALIZE_EMBEDDINGS

Purpose: normalize vectors for cosine similarity.

Example:

```env
NORMALIZE_EMBEDDINGS=true
```

### RETRIEVAL_TOP_K

Purpose: number of chunks returned by first retrieval stage.

Example:

```env
RETRIEVAL_TOP_K=10
```

### RERANK_TOP_K

Purpose: number of chunks kept after reranking.

Example:

```env
RERANK_TOP_K=5
```

### MIN_RETRIEVAL_SCORE

Purpose: threshold for dense retrieval.

Example:

```env
MIN_RETRIEVAL_SCORE=0.25
```

### USE_RERANKER

Purpose: enable CrossEncoder reranking.

Example:

```env
USE_RERANKER=true
```

### RERANKER_MODEL

Purpose: CrossEncoder model.

Example:

```env
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

### DEBUG_RETRIEVAL_SCORES

Purpose: log retrieval and reranking details.

Example:

```env
DEBUG_RETRIEVAL_SCORES=true
```

### TESSERACT_CMD

Purpose: Windows path to Tesseract binary.

Example:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

## Hugging Face Token

Optional:

```env
HF_TOKEN=your-token
```

The app does not read `HF_TOKEN` directly, but Hugging Face libraries can use it for downloads/rate limits.
