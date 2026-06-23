# Debugging Guide

This guide explains how to debug common problems in this multimodal RAG application.

## 1. Check Backend Is Running

Start backend:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Check root:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/" -Method Get
```

Expected:

```json
{
  "message": "Multimodal RAG backend is running",
  "docs": "http://127.0.0.1:8000/docs"
}
```

If it fails:

- Check terminal for import errors.
- Confirm virtual environment is activated.
- Confirm dependencies are installed.

## 2. Check Swagger UI

Open:

```text
http://127.0.0.1:8000/docs
```

If Swagger does not open:

- Backend is not running.
- Port is different.
- Uvicorn crashed.

## 3. Check Frontend

There is no frontend in this repository.

Use:

- Swagger UI
- PowerShell `Invoke-RestMethod`
- Python scripts

## 4. Check If Vectors Exist

API:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
```

Direct terminal:

```powershell
.\venv\Scripts\python.exe -c "from app.vectorstores.qdrant_store import QdrantStore; print(QdrantStore().count_vectors())"
```

Expected:

```text
number greater than 0
```

Current rebuilt index had around:

```text
755
```

If vector count is `0`:

1. Run ingestion.
2. Check `data/` has supported files.
3. Check ingestion warnings/errors.
4. Check Qdrant local path.

## 5. Regenerate Vectors

Direct command:

```powershell
.\venv\Scripts\python.exe -c "from app.ingestion.ingestion_service import IngestionService; print(IngestionService().ingest_all(force=True, reset=True))"
```

API command:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/ingest" -Method Post -ContentType "application/json" -Body '{"reset":true,"force":true}'
```

Use this after changing:

- ingestion code
- OCR logic
- metadata logic
- chunking logic
- embedding model

## 6. Inspect Stored Chunks

Example:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/debug/chunks" -Method Post -ContentType "application/json" -Body '{"file_name":"genai.pdf"}'
```

Look for:

- `chunk_type`
- `content_type`
- `title`
- `caption`
- `figure_number`
- `contains_diagram`
- `contains_chart`
- `text_preview`

For visual content, you want chunks like:

```text
diagram_summary
chart_summary
image_description
page_ocr
image_ocr
```

## 7. Debug Retrieved Chunks

Example:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/debug/search" -Method Post -ContentType "application/json" -Body '{"question":"What is taxonomy of GenAI-related disciplines?"}'
```

Good result:

```text
genai.pdf | page=1 | chunk_type=diagram_summary
```

For `What was the revenue in Q4 2024?`, good result:

```text
company_chart.pdf | chunk_type=chart_summary | year=2024
```

If wrong source appears first:

- Check query parser output by reading `app/rag/query_parser.py`.
- Check metadata in `POST /debug/chunks`.
- Confirm vectors were regenerated after metadata changes.
- Enable debug logs.

## 8. Enable Retrieval Debug Logs

Set in `.env`:

```env
DEBUG_RETRIEVAL_SCORES=true
```

Restart backend.

The retriever logs:

- parsed filters
- retrieved chunks before rerank
- chunks after rerank
- final chunks sent to LLM

Relevant code:

- `Retriever._log_hits`
- `Reranker.rerank`
- `RAGGraph._build_context_chunks`

## 9. Debug Wrong-Source Answers

Use this process:

1. Run `/debug/search`.
2. Check first chunk.
3. Check `file_name`.
4. Check `year`, `quarter`, `metric_names`.
5. Check `chunk_type`.
6. Check `text_preview`.
7. If retrieval is wrong, fix retriever/query metadata.
8. If retrieval is right but answer is wrong, fix prompt/answer generator.

Common causes:

- Old vectors still stored.
- Metadata missing.
- Query did not include year.
- OCR did not extract visual labels.
- Reranker pushed wrong chunk up.
- Azure OpenAI ignored instructions.

## 10. Debug "I Could Not Find This Information"

Checklist:

1. Does `/health` show vectors > 0?
2. Does `/debug/chunks` show useful chunks?
3. Does `/debug/search` retrieve relevant chunks?
4. Does the chunk text contain the answer?
5. Is `MIN_RETRIEVAL_SCORE` too high?
6. Is the year/file filter too strict?
7. Did you regenerate vectors after code changes?

For visual questions:

- Confirm `page_ocr` exists.
- Confirm `diagram_summary` or `chart_summary` exists.
- Confirm `contains_diagram` or `contains_chart` is `true`.

## 11. Debug Azure OpenAI Errors

Relevant file:

```text
app/rag/answer_generator.py
```

Required variables:

```env
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=
AZURE_OPENAI_DEPLOYMENT=
USE_AZURE_OPENAI=true
```

Common errors:

- Wrong deployment name.
- API key invalid.
- Endpoint URL wrong.
- Model does not support chat completions.
- Network issue.

Important:

`AZURE_OPENAI_DEPLOYMENT` is the Azure deployment name, not only the model name.

Fallback behavior:

If Azure fails, the app logs the error and returns extractive context:

```text
I found relevant information in the uploaded documents, but the AI answer generation service is unavailable...
```

## 12. Debug Vision Model Errors

Relevant file:

```text
app/ingestion/vision_processor.py
```

Variable:

```env
USE_OPENAI_VISION=true
```

If `false`, the app uses Tesseract OCR only.

If vision fails:

- The app logs a warning.
- It continues with OCR fallback.

This is intentional so ingestion does not fail because of vision quota or API issues.

## 13. Debug Tesseract OCR

Check Tesseract:

```powershell
tesseract --version
```

If Windows cannot find it, set:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Relevant file:

```text
app/ingestion/image_ocr.py
```

Common symptoms:

- OCR text is empty.
- Warnings: `Image processed, but no readable OCR text found.`
- Visual chunks are weak.

Fixes:

- Install Tesseract.
- Set `TESSERACT_CMD`.
- Use better image resolution.
- Enable vision model.

## 14. Debug Hugging Face Model Loading

Embedding model:

```env
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Reranker:

```env
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

Important code:

```python
local_files_only=True
```

This means the embedding model must already be cached locally. If it is not cached, the app falls back to deterministic embeddings.

Symptoms:

- Logs say model failed to load.
- Retrieval quality is poor.

Fixes:

- Download model once with internet.
- Disable `local_files_only` if appropriate.
- Use a model path available on disk.

## 15. Debug Qdrant Errors

Local path:

```env
QDRANT_LOCAL_PATH=./vectorstores/qdrant_local
```

Remote URL:

```env
QDRANT_URL=http://localhost:6333
```

Run Qdrant remote:

```powershell
docker run -p 6333:6333 -p 6334:6334 -v ${PWD}/qdrant_storage:/qdrant/storage qdrant/qdrant
```

Common local warning:

```text
ImportError: sys.meta_path is None, Python is likely shutting down
```

Meaning:

- Python command finished.
- Qdrant cleanup ran during interpreter shutdown.
- Usually harmless if output already showed successful vector count or ingestion result.

## 16. Debug Locked Local Qdrant Store

If local Qdrant complains about lock:

1. Stop backend.
2. Close Python scripts using Qdrant.
3. Restart VS Code terminal.
4. Try again.

If needed, clear index:

```powershell
Remove-Item -LiteralPath ".\vectorstores\qdrant_local" -Recurse -Force
Remove-Item -LiteralPath ".\.index_meta.json" -Force
```

Then regenerate vectors.

## 17. Debug Tests

Run tests:

```powershell
.\venv\Scripts\python.exe -m pytest
```

Current expected:

```text
23 passed
```

If tests fail:

- Read the first failure.
- Check which file and line failed.
- Re-run only one test:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_rag.py -k visual
```

## 18. Debug Final Context Sent To LLM

Set:

```env
DEBUG_RETRIEVAL_SCORES=true
```

Then ask a question through `/chat`.

Logs will show:

```text
FINAL CHUNKS SENT TO LLM:
```

This is the best way to see whether the LLM received the correct evidence.

## 19. Best Debugging Flow

For any bad answer:

```text
/health
  -> vector_count > 0?

/debug/chunks
  -> answer exists in stored chunks?

/debug/search
  -> correct chunks retrieved?

DEBUG_RETRIEVAL_SCORES=true
  -> correct chunks sent to LLM?

/chat
  -> final answer correct?
```
