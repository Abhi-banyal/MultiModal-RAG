# Ingestion Workflow

This document explains exactly what happens when vectors are generated.

## What Ingestion Means

Ingestion means:

```text
source files -> extract useful content -> chunk text -> attach metadata -> embed chunks -> store vectors
```

In this project, ingestion is handled mainly by:

- `app/ingestion/ingestion_service.py`
- `app/ingestion/docling_extractor.py`
- `app/ingestion/vision_processor.py`
- `app/ingestion/chunker.py`
- `app/vectorstores/qdrant_store.py`

## Commands That Start Ingestion

Option 1: through API

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/ingest" -Method Post -ContentType "application/json" -Body '{"reset":true,"force":true}'
```

Option 2: direct terminal command

```powershell
.\venv\Scripts\python.exe -c "from app.ingestion.ingestion_service import IngestionService; print(IngestionService().ingest_all(force=True, reset=True))"
```

Option 3: validation script

```powershell
.\venv\Scripts\python.exe scripts/test_rag_pipeline.py
```

## First File That Runs

If you use `POST /ingest`, the flow begins in `app/api/routes.py`:

```python
@router.post("/ingest", response_model=schemas.IngestResponse)
def ingest(req: schemas.IngestRequest = Body(default_factory=schemas.IngestRequest)):
    service = IngestionService()
    result = service.ingest_all(force=req.force, reset=req.reset)
```

Then `IngestionService.ingest_all()` runs.

If you use the direct terminal command, it calls `IngestionService().ingest_all(...)` directly.

## Full Ingestion Flow

```text
data/
  |
  v
list_data_files()
  |
  v
_ingest_file()
  |
  +--> .txt -> load_txt() -> split_text_to_chunks()
  +--> .csv -> load_csv_as_markdown() -> table_summary chunk
  +--> .pdf -> extract_pdf() -> text/OCR/images/tables/visual summaries
  +--> image -> process_image() -> OCR/vision/visual summaries
  |
  v
create_chunk_docs()
  |
  v
QdrantStore.upsert_documents()
  |
  v
SentenceTransformer embeddings
  |
  v
Qdrant local/remote collection
```

## Step 1: Find Files In `data/`

File: `app/ingestion/loaders.py`

```python
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".csv", ".png", ".jpg", ".jpeg"}
```

Only these files are indexed.

```python
files = [p for p in data_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
```

Explanation:

- `data_dir.rglob("*")` scans files recursively.
- `p.is_file()` skips folders.
- `p.suffix.lower()` checks file extension.

## Step 2: Create Base Metadata

File: `app/ingestion/metadata.py`

```python
def file_meta(path: Path) -> dict:
    hash_value = file_hash(path)
```

The app creates a SHA-256 hash for each file. This hash is used to detect changes.

Metadata includes:

- `document_id`
- `file_hash`
- `source_file`
- `file_name`
- `file_path`
- `source_path`
- `file_type`
- `document_type`
- `title`
- `last_modified`
- `indexed_at`

## Step 3: Skip Unchanged Files

File: `app/ingestion/ingestion_service.py`

```python
if (
    config.INGEST_SKIP_UNCHANGED
    and not force
    and not embedding_model_changed
    and previous_hash == current_hash
    and existing_vectors > 0
):
    skipped_files.append(...)
    continue
```

This means unchanged files are skipped unless `force=True`.

Use `force=True` when:

- You changed extraction logic.
- You changed chunking.
- You changed metadata logic.
- You want to rebuild all vectors.

Use `reset=True` when:

- You want to clear the vector collection first.
- You changed embedding model dimensions.

## Step 4: Process Text Files

File: `IngestionService._ingest_text_file`

```python
txt = load_txt(path)
chunks = split_text_to_chunks(txt)
return create_chunk_docs(self._meta_for(path, extraction_method="text"), chunks, "text"), []
```

Flow:

```text
.txt file -> read text -> split into chunks -> create chunk docs
```

## Step 5: Process CSV Files

File: `IngestionService._ingest_csv_file`

```python
table_text = load_csv_as_markdown(path)
```

CSV rows are converted into markdown tables. Then they are stored as `table_summary` chunks.

## Step 6: Process Standalone Images

File: `IngestionService._ingest_image_file`

```python
with Image.open(path) as image:
    result = process_image(image.convert("RGB"))
```

Flow:

```text
image file -> Pillow opens image -> Tesseract OCR -> optional vision model -> image_ocr chunk -> visual summary chunks
```

If OCR finds text, the text is stored.

If the image matches known visual patterns, `visual_summaries_for_content()` can create:

- `diagram_summary`
- `image_description`

Example: `cnn_diagram.png` creates a CNN architecture summary.

## Step 7: Process PDFs

File: `app/ingestion/docling_extractor.py`

Each page produces:

- selectable text
- extracted tables
- embedded images
- rendered page image

Actual code:

```python
text = page.get_text("text") or ""
tables = _extract_tables_with_pdfplumber(path, page_index)
images = _extract_images_with_pymupdf(page)
rendered_image = _render_page_image(page)
```

### PDF Text Chunks

In `IngestionService._ingest_pdf_file`:

```python
create_chunk_docs(
    {**base_meta, "extraction_method": "pdf_text", "chunk_type": "pdf_text"},
    split_text_to_chunks(page_text),
    "pdf_text",
)
```

This creates chunks from selectable PDF text.

### Rendered Page OCR Chunks

Every PDF page is rendered as an image and sent through OCR:

```python
rendered_image = page.get("rendered_image")
result = process_image(rendered_image)
```

This creates `page_ocr` chunks. This is important for diagrams embedded on text-heavy pages, such as `genai.pdf` page 1.

### Embedded Image OCR Chunks

PDF embedded images are also processed:

```python
for image in page.get("images", []):
    result = process_image(image)
```

This creates `image_ocr` chunks.

### Visual Summary Chunks

After OCR, visual content is summarized:

```python
for summary in visual_summaries_for_content(path, page_number, rendered_text):
    create_chunk_docs(..., [summary["text"]], summary["content_type"])
```

Possible chunk types:

- `image_description`
- `diagram_summary`
- `chart_summary`

### Table Summary Chunks

Tables are converted to markdown and stored:

```python
section_title = f"Table {table_index}"
chunk_type = "table_summary"
```

## Step 8: Visual Analyzer

File: `app/ingestion/visual_analyzer.py`

This file creates clean summaries for visual content.

Example: GenAI taxonomy:

```python
def genai_taxonomy_summary(path: Path, page_number: int, text: str):
```

It checks:

- file is `genai.pdf`
- page is `1`
- OCR text contains labels such as Artificial Intelligence, Machine Learning, Deep Learning, Generative

Then it creates a self-contained `diagram_summary`.

Example summary content:

```text
File: genai.pdf. Page: 1. Figure 1: A taxonomy of GenAI-related disciplines.
Artificial Intelligence is the broadest outer category.
Machine Learning is inside Artificial Intelligence.
Deep Learning is inside Machine Learning.
Generative AI is inside Deep Learning.
```

## Step 9: Chunk Creation

File: `app/ingestion/chunker.py`

Main function:

```python
def create_chunk_docs(source_meta: Dict[str, Any], texts: Sequence[str], content_type: str) -> List[Dict[str, Any]]:
```

Each output document has:

```python
{
    "id": chunk_id,
    "text": format_chunk_text(chunk_meta, clean_text),
    "metadata": {...}
}
```

Important metadata:

- `file_name`
- `source_path`
- `page_number`
- `content_type`
- `chunk_type`
- `title`
- `caption`
- `figure_number`
- `year`
- `quarter`
- `metric_names`
- `visual_type`
- `contains_chart`
- `contains_diagram`
- `contains_table`
- `contains_image`
- `extraction_method`

## Step 10: Chunk Text Format

The app does not embed raw text only. It adds a header:

```text
Document: genai.pdf
Page: 1
Chunk type: diagram_summary
Title: A taxonomy of GenAI-related disciplines
Caption: Figure 1: A taxonomy of GenAI-related disciplines.
Figure: 1

Content:
...
```

This makes each chunk self-contained.

## Step 11: Embedding Generation

File: `app/vectorstores/qdrant_store.py`

```python
texts = [doc["text"] for doc in docs]
vectors = self._embed_texts(texts)
```

Embedding model:

```python
sentence-transformers/all-MiniLM-L6-v2
```

Each chunk text becomes a numeric vector.

## Step 12: Qdrant Insertion

File: `QdrantStore.upsert_documents`

```python
points.append(PointStruct(id=doc_id, vector=vectors[index], payload=payload))
self.client.upsert(collection_name=self.collection, points=points)
```

Each Qdrant point contains:

- ID
- vector
- payload metadata
- original chunk text

## Where Vectors Are Stored

Default local path:

```text
vectorstores/qdrant_local
```

Configured by:

```env
QDRANT_LOCAL_PATH=./vectorstores/qdrant_local
```

## What Happens If You Delete Vectorstore

If you delete:

```text
vectorstores/qdrant_local
.index_meta.json
```

then run ingestion again, the app:

1. Creates a new local Qdrant store.
2. Reprocesses files from `data/`.
3. Recreates chunks and metadata.
4. Recreates embeddings.
5. Stores new vectors.

## Verify Vectors

PowerShell:

```powershell
.\venv\Scripts\python.exe -c "from app.vectorstores.qdrant_store import QdrantStore; print(QdrantStore().count_vectors())"
```

Expected:

```text
755
```

The number can change if files or chunking logic changes.

## Inspect Chunks

Use API:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/debug/chunks" -Method Post -ContentType "application/json" -Body '{"file_name":"genai.pdf"}'
```

Look for:

- `chunk_type: diagram_summary`
- `chunk_type: page_ocr`
- `contains_diagram: true`
- `figure_number: 1`

## Current Weaknesses And Improvements

Current strengths:

- PDF text extraction works.
- Rendered page OCR captures visual labels.
- Chart and diagram summaries are indexed.
- Visual-aware retrieval is implemented.

Current weak points:

- Some visual summaries are deterministic for known sample files.
- Tesseract OCR can misread labels.
- `USE_OPENAI_VISION=false` by default, so advanced vision captions are not always generated.
- Local embedding model must be cached because `local_files_only=True`.

Possible improvements:

- Enable `USE_OPENAI_VISION=true` for richer generic image descriptions.
- Use Azure AI Document Intelligence for better PDF/layout extraction.
- Add automated chart value extraction instead of deterministic sample-specific summaries.
- Add image preprocessing before OCR.
- Store bounding boxes for figures/tables if layout accuracy matters.
