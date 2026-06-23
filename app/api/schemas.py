from typing import List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    vector_store: Optional[str] = None
    vector_store_backend: Optional[str] = None
    collection: Optional[str] = None
    embedding_model: Optional[str] = None
    vector_count: Optional[int] = None


class FileIssue(BaseModel):
    file_name: str
    file_path: str
    message: str


class IngestResponse(BaseModel):
    status: str
    vector_store: str
    collection: str
    total_files: int
    processed_files: List[str] = Field(default_factory=list)
    failed_files: List[FileIssue] = Field(default_factory=list)
    skipped_files: List[FileIssue] = Field(default_factory=list)
    total_chunks_created: int
    vectors_stored: int
    vector_store_count_after_ingest: int
    warnings: List[FileIssue] = Field(default_factory=list)
    errors: List[FileIssue] = Field(default_factory=list)


class IngestRequest(BaseModel):
    force: bool = False
    reset: bool = False


class ChatRequest(BaseModel):
    question: str


class DebugSearchRequest(BaseModel):
    question: str


class DebugChunksRequest(BaseModel):
    file_name: str


class Source(BaseModel):
    file_name: str
    page_number: Optional[int] = None
    content_type: str
    chunk_type: Optional[str] = None
    title: Optional[str] = None
    caption: Optional[str] = None
    figure_number: Optional[str] = None
    visual_type: Optional[str] = None
    year: Optional[int] = None
    quarter: Optional[str | list[str]] = None
    score: Optional[float] = None
    rerank_score: Optional[float] = None
    matched_text_preview: Optional[str] = None
    visual_url: Optional[str] = None
    visual_label: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[Source] = Field(default_factory=list)


class DocumentMeta(BaseModel):
    file_name: str
    file_path: str
    file_type: str
    last_indexed: Optional[str] = None
