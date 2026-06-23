# RAG Workflow

This document explains query-time behavior: what happens when the user asks a question.

## Full Query Flow

```text
user question
  |
  v
POST /chat
  |
  v
RAGGraph.run()
  |
  v
parse query filters
  |
  v
Qdrant search
  |
  v
metadata + keyword scoring
  |
  v
CrossEncoder reranking
  |
  v
build final context
  |
  v
Azure OpenAI answer
  |
  v
answer + sources
```

## Main Files

- `app/api/routes.py`: receives API request.
- `app/rag/graph.py`: orchestrates the pipeline.
- `app/rag/query_parser.py`: understands query intent.
- `app/rag/retriever.py`: retrieves chunks.
- `app/vectorstores/qdrant_store.py`: embeds query and searches Qdrant.
- `app/rag/reranker.py`: reranks chunks.
- `app/rag/prompts.py`: builds final prompt.
- `app/rag/answer_generator.py`: calls Azure OpenAI or fallback.

## Step 1: User Calls `/chat`

File: `app/api/routes.py`

```python
@router.post("/chat", response_model=schemas.ChatResponse)
def chat(req: schemas.ChatRequest):
    answer, sources = get_rag_graph().run(req.question)
```

The JSON body looks like:

```json
{
  "question": "What is taxonomy of GenAI-related disciplines?"
}
```

## Step 2: RAGGraph Receives The Question

File: `app/rag/graph.py`

```python
def _receive_question(self, state):
    question = (state.get("question") or "").strip()
    return {**state, "question": question, "query": question}
```

This cleans whitespace and copies the question into `query`.

## Step 3: Query Parsing

File: `app/rag/query_parser.py`

```python
query_filters = parse_query_filters(query)
```

The parser detects:

- year: `2024`, `2025`
- quarter: `Q1`, `Q2`, `Q3`, `Q4`
- metric: `revenue`, `net_profit`, etc.
- file name: `genai.pdf`
- page number: `page 1`
- figure number: `Figure 1`
- visual intent: `diagram`, `chart`, `taxonomy`, `architecture`

Example:

```python
parse_query_filters("Explain Figure 1 in genai.pdf")
```

Result includes:

```python
{
    "file_name": "genai.pdf",
    "figure_number": "1",
    "visual": True,
    "diagram_intent": True
}
```

## Step 4: Retrieval

File: `app/rag/retriever.py`

```python
candidates = self.retriever.retrieve(
    state["query"],
    top_k=config.RETRIEVAL_TOP_K,
    query_filters=state.get("query_filters"),
)
```

The retriever:

1. Builds metadata filters.
2. Sends query to Qdrant.
3. Applies keyword and metadata boosts.
4. Returns top candidates.

## Step 5: Query Embedding

File: `app/vectorstores/qdrant_store.py`

```python
query_vector = self._embed_texts([query])[0]
```

The user question is converted into the same vector space as chunks.

Embedding model:

```env
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

This is local Hugging Face/SentenceTransformers, not Azure OpenAI embeddings.

## Step 6: Qdrant Search

File: `QdrantStore.search`

```python
response = self.client.query_points(
    collection_name=self.collection,
    query=query_vector,
    query_filter=query_filter,
    limit=top_k,
)
```

Qdrant returns chunks whose vectors are close to the query vector.

## Step 7: Metadata Filters

If the query says `2024`, the retriever applies:

```python
store_filter["year"] = query_filters["year"]
```

If the query says `genai.pdf`, it applies:

```python
store_filter["file_name"] = query_filters["file_name"]
```

If the query says `Figure 1`, it applies:

```python
store_filter["figure_number"] = query_filters["figure_number"]
```

This prevents wrong-year or wrong-file chunks from dominating.

## Step 8: Metadata And Keyword Scoring

File: `app/rag/retriever.py`

```python
metadata_score = metadata_priority_score(hit.get("metadata", {}), query_filters)
combined = metadata_score + dense_score + (0.35 * keyword_score) + rrf_score
```

The final retrieval score combines:

- vector similarity
- keyword overlap
- metadata match
- small rank fusion score

For visual questions, `metadata_priority_score` boosts:

- `diagram_summary`
- `chart_summary`
- `image_description`
- `image_ocr`
- `page_ocr`
- `contains_chart`
- `contains_diagram`

## Step 9: Reranking

File: `app/rag/reranker.py`

```python
pairs = [[query, candidate.get("text", "")[:4000]] for candidate in candidates]
scores = self.model.predict(pairs)
```

The CrossEncoder reads query and chunk together. It is slower but usually more accurate than vector search alone.

Final rerank score:

```python
final_score = candidate["score"] + rerank_score + metadata_priority_score(...)
```

This keeps visual/year metadata important even after reranking.

## Vector Search vs Reranking

Vector search:

- Fast.
- Searches many chunks.
- Uses embedding similarity.
- May confuse similar documents.

Reranking:

- Slower.
- Looks at fewer chunks.
- Directly scores query and chunk together.
- Improves final ordering.

## Step 10: Clarification Behavior

File: `RAGGraph._maybe_ask_clarification`

If the user asks:

```text
What was the revenue in Q4?
```

and retrieved chunks include both 2024 and 2025, the app responds:

```text
Please specify which year you mean (2024 or 2025) so I do not mix results from different documents.
```

This prevents guessing between `company_chart.pdf` and `company_report.pdf`.

## Step 11: Build Final Context

File: `RAGGraph._build_context_chunks`

```python
context_chunks = [
    {
        "id": item.get("id"),
        "text": item.get("text", ""),
        "metadata": item.get("metadata", {}),
        "score": item.get("score"),
        "rerank_score": item.get("rerank_score"),
    }
    for item in ranked
]
```

This prepares the chunks that will be sent to the answer generator.

## Step 12: Prompt Construction

File: `app/rag/prompts.py`

```python
prompt = build_prompt(context_chunks, question)
```

The prompt includes:

- instructions
- source metadata
- retrieved context
- user question

Visual instruction example:

```text
Use image_description, chart_summary, diagram_summary, image_ocr, and page_ocr chunks when the question is visual.
```

## Step 13: Azure OpenAI Answer

File: `app/rag/answer_generator.py`

```python
response = self.client.chat.completions.create(
    model=self.model,
    messages=[
        {"role": "system", "content": "..."},
        {"role": "user", "content": prompt},
    ],
    temperature=0.1,
)
```

Important:

- `model` is the Azure deployment name.
- The app uses retrieved chunks only.
- If Azure fails, it falls back to extractive answer.

## Step 14: Sources

File: `AnswerGenerator._build_sources`

Each source includes:

- `file_name`
- `page_number`
- `content_type`
- `chunk_type`
- `title`
- `caption`
- `figure_number`
- `visual_type`
- `year`
- `quarter`
- `score`
- `rerank_score`
- `matched_text_preview`

## Data Flow Between Files

```text
app/main.py
  -> app/api/routes.py
      -> app/rag/graph.py
          -> app/rag/query_parser.py
          -> app/rag/retriever.py
              -> app/vectorstores/qdrant_store.py
          -> app/rag/reranker.py
          -> app/rag/answer_generator.py
              -> app/rag/prompts.py
```

Ingestion data flow:

```text
app/api/routes.py
  -> app/ingestion/ingestion_service.py
      -> loaders.py
      -> docling_extractor.py
      -> image_ocr.py
      -> vision_processor.py
      -> visual_analyzer.py
      -> chunker.py
      -> app/vectorstores/qdrant_store.py
```

## Multimodal Query Examples

Question:

```text
What is taxonomy of GenAI-related disciplines?
```

Expected top chunk:

```text
genai.pdf | page=1 | chunk_type=diagram_summary
```

Question:

```text
Explain the CNN architecture diagram.
```

Expected top chunk:

```text
cnn_diagram.png | chunk_type=diagram_summary
```

Question:

```text
What was the revenue in Q4 2024?
```

Expected top chunk:

```text
company_chart.pdf | page=1 | chunk_type=chart_summary
```

## Embeddings And Reranking Summary

Embeddings:

- Convert text into vectors.
- Used for chunk search and query search.
- Local model: `sentence-transformers/all-MiniLM-L6-v2`.
- No Azure tokens are used for embeddings.

Reranking:

- Uses `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- Scores query/chunk pairs.
- Helps choose best chunks after vector search.

## Current Weaknesses

- Some visual summaries are hard-coded for known sample files.
- Generic visual captions are only as good as OCR unless `USE_OPENAI_VISION=true`.
- Tesseract can make OCR mistakes like `GenAl` instead of `GenAI`.
- CrossEncoder loading can be slow.
- Local Qdrant cleanup may print a harmless shutdown warning in one-off scripts.

## Improvement Ideas

- Use Azure OpenAI vision for every rendered page.
- Use Azure AI Document Intelligence for layout and figure extraction.
- Store page screenshots or cropped figure images as separate assets.
- Add user-upload endpoint.
- Add frontend UI for chat, ingestion, and debug search.
