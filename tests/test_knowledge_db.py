import json
from pathlib import Path

from knowledge_db import load_chunks, sync_from_corpus


def test_sync_knowledge_corpus_upserts(tmp_path: Path):
    db_path = tmp_path / "knowledge.sqlite3"
    corpus = [{
        "chunk_id": "c1",
        "source_id": "DOC-1",
        "title": "문서",
        "source_type": "official_manual",
        "text": "민원 대응 내용",
        "locator": "p1",
        "pdf_page": 1,
        "verification_status": "verified",
        "authority_rank": 4,
        "canonical": True,
    }]
    first = sync_from_corpus(corpus, db_path)
    assert first["inserted"] == 1
    second = sync_from_corpus([{**corpus[0], "text": "수정된 내용"}], db_path)
    assert second["updated"] == 1
    rows = load_chunks(db_path)
    assert len(rows) == 1
    assert rows[0]["text"] == "수정된 내용"
