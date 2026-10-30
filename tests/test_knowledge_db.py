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


def test_sync_prunes_stale_chunks(tmp_path: Path):
    db_path = tmp_path / "knowledge.sqlite3"
    first = [{
        "chunk_id": "old", "source_id": "DOC", "title": "문서",
        "source_type": "official_manual", "text": "예전 내용",
        "locator": "p1", "verification_status": "pending",
    }]
    sync_from_corpus(first, db_path)
    second = [{
        "chunk_id": "new", "source_id": "DOC", "title": "문서",
        "source_type": "official_manual", "text": "새 내용",
        "locator": "p2", "verification_status": "pending",
    }]
    result = sync_from_corpus(second, db_path, prune_missing=True)
    assert result["deleted"] == 1
    rows = load_chunks(db_path)
    assert [x["chunk_id"] for x in rows] == ["new"]
