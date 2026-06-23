import csv
from pathlib import Path
from typing import List
from ..core import config

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".csv", ".png", ".jpg", ".jpeg"}


def list_data_files() -> List[Path]:
    data_dir = config.DATA_DIR
    if not data_dir.exists():
        return []
    files = [p for p in data_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
    return files


def load_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def load_csv_as_markdown(path: Path) -> str:
    rows = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            rows.append([cell.strip() for cell in row])
    if not rows:
        return ""

    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    header = padded[0]
    separator = ["---"] * width
    body = padded[1:]

    def fmt(row: List[str]) -> str:
        return "| " + " | ".join(cell.replace("\n", " ") for cell in row) + " |"

    lines = [fmt(header), fmt(separator)]
    lines.extend(fmt(row) for row in body)
    return "\n".join(lines)
