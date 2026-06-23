from pathlib import Path
from datetime import datetime, timezone

from ..utils.file_hash import file_hash
from .metadata_extractor import infer_document_type


def file_meta(path: Path) -> dict:
    hash_value = file_hash(path)
    title = path.stem.replace("_", " ").replace("-", " ").title()
    return {
        "document_id": hash_value,
        "file_hash": hash_value,
        "source_file": path.name,
        "file_name": path.name,
        "file_path": str(path.resolve()),
        "source_path": str(path.resolve()),
        "file_type": path.suffix.lower().lstrip('.'),
        "document_type": infer_document_type(path),
        "title": title,
        "last_modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
