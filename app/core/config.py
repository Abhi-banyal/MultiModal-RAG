from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = Field(default=Path("./data"))
    index_metadata_path: Path = Field(default=Path("./.index_meta.json"))

    vector_store: str = Field(
        default="local",
        validation_alias=AliasChoices("VECTOR_STORE", "VECTOR_DB_PROVIDER", "QDRANT_MODE"),
    )
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = Field(
        default="multimodal_rag",
        validation_alias=AliasChoices("QDRANT_COLLECTION", "QDRANT_COLLECTION_NAME"),
    )
    qdrant_local_path: Path = Field(default=Path("./vectorstores/qdrant_local"))
    reset_vector_store: bool = False
    force_reingest: bool = False
    ingest_skip_unchanged: bool = True

    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_device: str = "cpu"
    normalize_embeddings: bool = True

    retrieval_top_k: int = 10
    rerank_top_k: int = 5
    min_retrieval_score: float = 0.25
    use_reranker: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    debug_retrieval_scores: bool = False

    ocr_engine: str = "tesseract"
    tesseract_cmd: str = ""
    use_openai_vision: bool = False

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = ""
    azure_openai_deployment: str = ""
    use_azure_openai: bool = True

    def resolved_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()

    def resolved_index_metadata_path(self) -> Path:
        return self.index_metadata_path.expanduser().resolve()

    def resolved_qdrant_local_path(self) -> Path:
        return self.qdrant_local_path.expanduser().resolve()


settings = Settings()

DATA_DIR = settings.resolved_data_dir()
INDEX_METADATA_PATH = settings.resolved_index_metadata_path()

VECTOR_STORE = settings.vector_store.lower().strip()
VECTOR_DB_PROVIDER = VECTOR_STORE
QDRANT_URL = settings.qdrant_url
QDRANT_API_KEY = settings.qdrant_api_key
QDRANT_COLLECTION = settings.qdrant_collection
QDRANT_COLLECTION_NAME = QDRANT_COLLECTION
QDRANT_LOCAL_PATH = settings.resolved_qdrant_local_path()
RESET_VECTOR_STORE = settings.reset_vector_store
FORCE_REINGEST = settings.force_reingest
INGEST_SKIP_UNCHANGED = settings.ingest_skip_unchanged

EMBEDDING_PROVIDER = settings.embedding_provider
EMBEDDING_MODEL = settings.embedding_model
EMBEDDING_DEVICE = settings.embedding_device
NORMALIZE_EMBEDDINGS = settings.normalize_embeddings

RETRIEVAL_TOP_K = settings.retrieval_top_k
RERANK_TOP_K = settings.rerank_top_k
MIN_RETRIEVAL_SCORE = settings.min_retrieval_score
USE_RERANKER = settings.use_reranker
RERANKER_MODEL = settings.reranker_model
DEBUG_RETRIEVAL_SCORES = settings.debug_retrieval_scores

OCR_ENGINE = settings.ocr_engine
TESSERACT_CMD = settings.tesseract_cmd
USE_OPENAI_VISION = settings.use_openai_vision

AZURE_OPENAI_ENDPOINT = settings.azure_openai_endpoint
AZURE_OPENAI_API_KEY = settings.azure_openai_api_key
AZURE_OPENAI_API_VERSION = settings.azure_openai_api_version
AZURE_OPENAI_DEPLOYMENT = settings.azure_openai_deployment
USE_AZURE_OPENAI = settings.use_azure_openai
