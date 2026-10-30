import json
import re
from config import DATA_DIR


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[가-힣A-Za-z0-9]+", text.lower()))


def retrieve(query: str, top_k: int = 4) -> list[dict]:
    payload = json.loads((DATA_DIR / "manual_chunks.json").read_text(encoding="utf-8"))
    terms = tokenize(query)
    results = []
    for chunk in payload["chunks"]:
        doc_terms = tokenize(chunk["title"] + " " + chunk["text"] + " " + " ".join(chunk.get("tags", [])))
        score = len(terms & doc_terms) / max(1, len(terms))
        if score:
            results.append((score, chunk))
    results.sort(key=lambda x: x[0], reverse=True)
    return [{"score": round(s, 3), **c} for s, c in results[:top_k]]
