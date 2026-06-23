# Libraries Explained

This document explains the important libraries used by this project, where they appear, and the syntax used in the actual codebase.

## FastAPI

Why it is used:

- Builds the backend HTTP API.
- Provides Swagger UI at `/docs`.
- Validates request/response data with Pydantic models.

Where used:

- `app/main.py`
- `app/api/routes.py`

Actual code:

```python
from fastapi import FastAPI

app = FastAPI(title="Multimodal RAG Chatbot", lifespan=lifespan)
```

Explanation:

- `FastAPI` is the application class.
- `title` appears in Swagger UI.
- `lifespan` runs startup/shutdown code.

Actual route syntax:

```python
@router.post("/chat", response_model=schemas.ChatResponse)
def chat(req: schemas.ChatRequest):
    answer, sources = get_rag_graph().run(req.question)
    return {"answer": answer, "sources": sources}
```

Explanation:

- `@router.post("/chat")` means this function handles HTTP `POST /chat`.
- `response_model=schemas.ChatResponse` tells FastAPI the output shape.
- `req: schemas.ChatRequest` tells FastAPI to parse JSON into a Pydantic object.

Alternatives:

- Flask
- Django REST Framework
- Litestar

## Uvicorn

Why it is used:

- Runs the FastAPI application locally.

Where used:

- Command line, not imported directly in app code.

Command:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Explanation:

- `app.main` means file `app/main.py`.
- `app` means the FastAPI object inside that file.
- `--reload` restarts server when code changes.

Alternatives:

- Hypercorn
- Gunicorn with Uvicorn workers on Linux servers

## Pydantic

Why it is used:

- Defines API request and response schemas.
- Parses and validates environment variables through `pydantic-settings`.

Where used:

- `app/api/schemas.py`
- `app/core/config.py`

Actual API model:

```python
class ChatRequest(BaseModel):
    question: str
```

Explanation:

- `ChatRequest` is a JSON body model.
- The request must contain a string field named `question`.

Actual response model:

```python
class ChatResponse(BaseModel):
    answer: str
    sources: List[Source] = Field(default_factory=list)
```

Explanation:

- `answer` is required.
- `sources` defaults to an empty list.
- `Field(default_factory=list)` avoids sharing one list between instances.

Settings model:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
```

Explanation:

- `BaseSettings` reads environment variables.
- `env_file=".env"` reads your local `.env`.
- `extra="ignore"` ignores environment variables not declared in the class.

Alternatives:

- dataclasses
- marshmallow
- dynaconf

## pydantic-settings and `.env` Loading

Why it is used:

- Reads `.env` into strongly typed Python settings.

Where used:

- `app/core/config.py`

Actual code:

```python
settings = Settings()
DATA_DIR = settings.resolved_data_dir()
```

Explanation:

- `Settings()` loads defaults plus `.env`.
- `DATA_DIR` becomes a resolved absolute `Path`.

Important note:

- The project does not directly import `python-dotenv`.
- `.env` reading is handled through `pydantic-settings`.

## PyMuPDF / fitz

Why it is used:

- Reads PDFs.
- Extracts selectable text.
- Extracts embedded images.
- Renders each PDF page into an image for OCR.

Where used:

- `app/ingestion/docling_extractor.py`

Actual code:

```python
import fitz

with fitz.open(path) as doc:
    for page_index, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
```

Explanation:

- `fitz.open(path)` opens a PDF.
- `enumerate(..., start=1)` creates human page numbers: 1, 2, 3.
- `page.get_text("text")` extracts selectable PDF text.

Rendering syntax:

```python
pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
```

Explanation:

- `get_pixmap` renders the page as pixels.
- `Matrix(2, 2)` doubles resolution for better OCR.
- `alpha=False` avoids transparent background.

Alternatives:

- pypdf for text only
- pdf2image for rendering
- unstructured for richer document parsing

## pdfplumber

Why it is used:

- Extracts tables from PDF pages.

Where used:

- `app/ingestion/docling_extractor.py`

Actual code:

```python
with pdfplumber.open(path) as pdf:
    tables = pdf.pages[page_number - 1].extract_tables() or []
```

Explanation:

- `page_number - 1` converts human page number to zero-based list index.
- `extract_tables()` returns table rows and cells.
- `or []` prevents `None` errors.

Alternatives:

- camelot
- tabula-py
- PyMuPDF table extraction

## Pillow

Why it is used:

- Opens and converts images.
- Converts extracted PDF images to RGB.
- Saves images to memory before sending to vision models.

Where used:

- `docling_extractor.py`
- `image_ocr.py`
- `vision_processor.py`
- `ingestion_service.py`

Actual code:

```python
from PIL import Image

with Image.open(path) as image:
    result = process_image(image.convert("RGB"))
```

Explanation:

- `Image.open(path)` opens a file.
- `.convert("RGB")` makes image mode consistent for OCR/vision.

Alternatives:

- OpenCV
- imageio

## pytesseract

Why it is used:

- Runs Tesseract OCR from Python.

Where used:

- `app/ingestion/image_ocr.py`

Actual code:

```python
text = pytesseract.image_to_string(image)
```

Explanation:

- Sends a PIL image to Tesseract.
- Returns recognized text.

Windows setup:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Alternatives:

- Azure AI Document Intelligence
- EasyOCR
- PaddleOCR

## SentenceTransformers

Why it is used:

- Creates embeddings for chunks and user queries.
- Loads local Hugging Face embedding model.

Where used:

- `app/vectorstores/qdrant_store.py`
- `app/rag/reranker.py`

Embedding model code:

```python
self.model = SentenceTransformer(
    config.EMBEDDING_MODEL,
    device=config.EMBEDDING_DEVICE,
    local_files_only=True,
)
```

Explanation:

- `config.EMBEDDING_MODEL` defaults to `sentence-transformers/all-MiniLM-L6-v2`.
- `device` is usually `cpu`.
- `local_files_only=True` means the model must already exist in local cache.

Embedding syntax:

```python
embeddings = self.model.encode(
    texts,
    show_progress_bar=False,
    convert_to_numpy=True,
    normalize_embeddings=config.NORMALIZE_EMBEDDINGS,
)
```

Explanation:

- `texts` is a list of strings.
- Output is numeric vectors.
- Normalized vectors work well with cosine distance.

Alternatives:

- OpenAI embeddings
- Azure OpenAI embeddings
- Cohere embeddings
- bge-small/bge-base models

## Hugging Face Models

Why they are used:

- SentenceTransformers and CrossEncoder models are loaded from Hugging Face model format.

Models in this project:

- Embedding: `sentence-transformers/all-MiniLM-L6-v2`
- Reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2`

No Hugging Face token is required for public models, but setting `HF_TOKEN` may reduce rate-limit issues when downloading.

## Qdrant Client

Why it is used:

- Stores vectors.
- Searches for nearest chunks.
- Supports metadata payloads and filters.

Where used:

- `app/vectorstores/qdrant_store.py`

Remote connection:

```python
self.client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None, timeout=5)
```

Local connection:

```python
self.client = QdrantClient(path=str(config.QDRANT_LOCAL_PATH), force_disable_check_same_thread=True)
```

Create collection:

```python
self.client.create_collection(
    collection_name=self.collection,
    vectors_config=rest.VectorParams(size=self.embedding_dim, distance=rest.Distance.COSINE),
)
```

Insert points:

```python
points.append(PointStruct(id=doc_id, vector=vectors[index], payload=payload))
self.client.upsert(collection_name=self.collection, points=points)
```

Search:

```python
response = self.client.query_points(
    collection_name=self.collection,
    query=query_vector,
    query_filter=query_filter,
    limit=top_k,
)
```

Alternatives:

- FAISS
- Chroma
- Milvus
- Weaviate
- pgvector

## LangGraph

Why it is used:

- Builds the RAG workflow as a graph of steps.

Where used:

- `app/rag/graph.py`

Actual code:

```python
workflow = StateGraph(RAGState)
workflow.add_node("retrieve_context", self._retrieve_context)
workflow.add_edge("retrieve_context", "rerank_context")
return workflow.compile()
```

Explanation:

- `StateGraph` manages state between steps.
- Nodes are Python functions.
- Edges define execution order.

Important note:

- This project uses `langgraph`, not LangChain document loaders or chains.

Alternatives:

- Plain Python function pipeline
- LangChain chains
- LlamaIndex workflows

## Azure OpenAI / OpenAI Python SDK

Why it is used:

- Generates final answers.
- Optionally generates vision descriptions.

Where used:

- `app/rag/answer_generator.py`
- `app/ingestion/vision_processor.py`

Azure client code:

```python
self.client = AzureOpenAI(
    api_key=config.AZURE_OPENAI_API_KEY,
    api_version=config.AZURE_OPENAI_API_VERSION,
    azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
)
```

Chat completion:

```python
response = self.client.chat.completions.create(
    model=self.model,
    messages=[
        {"role": "system", "content": "You answer questions using only retrieved document context."},
        {"role": "user", "content": prompt},
    ],
    temperature=0.1,
)
```

Explanation:

- `model` is your Azure deployment name, not necessarily the base model name.
- `messages` is the chat conversation.
- `temperature=0.1` makes answers more deterministic.

Alternatives:

- Standard OpenAI
- Anthropic
- Gemini
- Local LLMs

## CrossEncoder Reranker

Why it is used:

- Improves ranking after vector search.
- Scores each `(query, chunk)` pair directly.

Where used:

- `app/rag/reranker.py`

Actual code:

```python
pairs = [[query, candidate.get("text", "")[:4000]] for candidate in candidates]
scores = self.model.predict(pairs)
```

Explanation:

- A CrossEncoder reads query and chunk together.
- It gives a relevance score.
- The app combines this with metadata priority.

Alternatives:

- Cohere rerank
- bge-reranker
- LLM reranking
- Reciprocal rank fusion only

## NumPy

Why it is used:

- Computes fallback vector similarity when JSON vector fallback is used.

Where used:

- `app/vectorstores/qdrant_store.py`

Actual code:

```python
score = float(np.dot(np.array(query_vector), np.array(vector)))
```

Explanation:

- Dot product measures similarity between vectors.
- Used only in fallback mode when Qdrant client is unavailable.

## pytest and httpx

Why they are used:

- `pytest` runs tests.
- `httpx` is used internally by FastAPI TestClient and packages.

Where used:

- `tests/`

Command:

```powershell
.\venv\Scripts\python.exe -m pytest
```

## Frontend Libraries

There is no frontend in this repository. The app is currently backend-only. You interact through:

- Swagger UI: `http://127.0.0.1:8000/docs`
- PowerShell REST commands
- Python scripts

## Important Python Syntax From This Project

Imports:

```python
from ..core import config, logging
```

This imports sibling package modules using a relative import. `..core` means go up one package from the current folder.

Class definition:

```python
class QdrantStore:
    def __init__(self):
        self.collection = config.QDRANT_COLLECTION
```

This creates an object. `__init__` runs when `QdrantStore()` is created. `self.collection` stores data on the object.

Function definition:

```python
def search(self, query: str, top_k: int = 5, filter: Optional[Dict[str, Any]] = None):
```

This function accepts a query string, an optional top-k number, and an optional metadata filter.

Try/except:

```python
try:
    self.client.get_collections()
except Exception as exc:
    logger.warning("Failed to connect to Qdrant at %s: %s", config.QDRANT_URL, exc)
```

This attempts risky code and handles failures without crashing the whole app.

List comprehension:

```python
texts = [doc["text"] for doc in docs]
```

This creates a list of text values from document dictionaries.

Dictionary merge:

```python
{**base_meta, "extraction_method": "page_ocr", "chunk_type": "page_ocr"}
```

This copies `base_meta` and overrides/adds specific fields.

Type hints:

```python
def ingest_all(self, force: bool = False, reset: bool = False) -> Dict[str, Any]:
```

This tells readers and tools that `force` and `reset` are booleans and the function returns a dictionary.
