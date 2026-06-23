import re


def clean_text(text: str) -> str:
    # basic cleaning: normalize whitespace
    return re.sub(r"\s+", " ", text).strip()
