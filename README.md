# Multimodal RAG Chatbot

FastAPI backend for ingesting text, PDF, and image files from `data/`, creating embeddings, storing them in Qdrant or a persistent local fallback, and answering questions with grounded sources.

## Windows Setup

Install dependencies:

```powershell
pip install -r requirements.txt
```

Check Tesseract:

```powershell
tesseract --version
```

If Windows cannot find Tesseract, set `TESSERACT_CMD` in `.env`:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Run Qdrant using Docker:

```powershell
docker run -p 6333:6333 -p 6334:6334 -v ${PWD}/qdrant_storage:/qdrant/storage qdrant/qdrant
```

Run FastAPI:

```powershell
python -m uvicorn app.main:app --reload
```

Open Swagger:

```text
http://127.0.0.1:8000/docs
```

Run `POST /ingest` from Swagger. For a full rebuild, use:

```json
{
  "reset": true,
  "force": true
}
```

## Vector Store Behavior

Set `VECTOR_STORE=qdrant` to use Qdrant at `QDRANT_URL` when it is reachable. If Qdrant is not running, the app logs a warning and uses the persistent local fallback at `QDRANT_LOCAL_PATH`.

Use these safe defaults in `.env`:

```env
USE_OPENAI_VISION=false
VECTOR_STORE=local
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=multimodal_rag
QDRANT_LOCAL_PATH=./vectorstores/qdrant_local
RESET_VECTOR_STORE=false
```

`RESET_VECTOR_STORE=false` prevents the collection from being recreated on every startup. Set it to `true` only when you intentionally want to clear and rebuild the vector store.

Use `reset=true` on `POST /ingest` when you changed the embedding model, want to clear stale vectors, or want a clean rebuild. Use `force=true` when files are unchanged but you want to re-run extraction and chunking.

## Azure OpenAI Vision

Ingestion does not require vision model calls. OCR runs first through Tesseract. Set `USE_OPENAI_VISION=true` only if you want optional Azure OpenAI image descriptions; quota errors and API failures are recorded as warnings and ingestion continues.

## Azure OpenAI Answers

Chat answer generation uses Azure OpenAI when `USE_AZURE_OPENAI=true`. Add these values to `.env`:

```env
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=
AZURE_OPENAI_DEPLOYMENT=
USE_AZURE_OPENAI=true
```

`AZURE_OPENAI_DEPLOYMENT` must be the Azure deployment name, not just the base model name. If Azure OpenAI is unavailable, `/chat` falls back to an extractive answer from retrieved chunks and still returns sources.

## Verify Ingestion

After `POST /ingest`, check the JSON response:

```json
{
  "status": "completed",
  "vector_store": "qdrant_local",
  "total_chunks_created": 12,
  "vectors_stored": 12,
  "vector_store_count_after_ingest": 12,
  "processed_files": ["machine_learning.txt"]
}
```

Vectors were generated successfully when `vector_store_count_after_ingest` is greater than `0`. `total_chunks_created` can be `0` when files are unchanged and existing vectors are already present; those files appear in `skipped_files`.

## RAG Workflow

1. Add files to `data/`.
2. Run the backend:

```powershell
python -m uvicorn app.main:app --reload
```

3. Open Swagger:

```text
http://127.0.0.1:8000/docs
```

4. Run `POST /ingest`:

```json
{
  "reset": true,
  "force": true
}
```

5. Test retrieval with `POST /debug/search`:

```json
{
  "question": "What does the Data security and IT usage policy say about passwords?"
}
```

6. Inspect chunks with `POST /debug/chunks`:

```json
{
  "file_name": "company_policy.pdf"
}
```

7. Ask the final question with `POST /chat`.

To confirm the correct file is retrieved, check the top results from `/debug/search`. To confirm vectors exist, check `GET /health` and verify `vector_count > 0`.

Run a local validation script:

```powershell
python scripts/test_rag_pipeline.py
```

Run tests:

```powershell
pytest
```
