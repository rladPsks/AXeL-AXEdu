import json
from pathlib import Path

import pytest

from ingestion.review import (
    _propose_law_overrides,
    apply_approved_overrides,
    build_review_package,
)


def test_proposes_distinct_current_and_future_article_18_versions():
    chunks = [
        {"document_id": "LAW-TEACHER-STATUS-21350", "chunk_id": "old18",
         "article_number": "18", "text": "제18조(위원회) 기존 제3항 내용",
         "version_status": "in_force"},
        {"document_id": "LAW-TEACHER-STATUS-21350", "chunk_id": "new18",
         "article_number": "18", "text": "제18조(위원회) ③ 교사 위원이 전체 위원 정수의 10분의 2 이상",
         "version_status": "in_force"},
    ]
    proposals = _propose_law_overrides(chunks)
    updates = {p["chunk_id"]: p["proposed_updates"] for p in proposals if p["operation"] == "update_chunk"}
    assert updates["old18"]["effective_to"] == "2026-11-19"
    assert updates["old18"]["version_status"] == "in_force"
    assert updates["new18"]["effective_from"] == "2026-11-20"
    assert updates["new18"]["version_status"] == "scheduled"
    assert updates["new18"]["verification_status"] == "pending"
    assert all(
        p.get("proposed_updates", {}).get("verification_status", "pending") == "pending"
        for p in proposals if p["operation"] == "update_chunk"
    )
    transition29 = next(
        p for p in proposals
        if p["proposal_id"] == "LAW21717-ADD-TRANSITION-ARTICLE-29"
    )
    assert "중인 교육활동보호센터" in transition29["proposed_chunk"]["text"]


def test_proposes_article_19_and_29_effective_dates():
    chunks = []
    for article in ("19", "29"):
        chunks.extend([
            {"document_id": "LAW-TEACHER-STATUS-21350", "chunk_id": article+"old",
             "article_number": article, "text": "old", "version_status": "in_force"},
            {"document_id": "LAW-TEACHER-STATUS-21350", "chunk_id": article+"new",
             "article_number": article, "text": "new", "version_status": "scheduled"},
        ])
    proposals = _propose_law_overrides(chunks)
    updates = {p["chunk_id"]: p["proposed_updates"] for p in proposals if p["operation"] == "update_chunk"}
    assert updates["19old"]["effective_to"] == "2026-12-02"
    assert updates["19new"]["effective_from"] == "2026-12-03"
    assert updates["29old"]["effective_to"] == "2026-12-02"
    assert updates["29new"]["effective_from"] == "2026-12-03"
    additions = [p for p in proposals if p["operation"] == "add_chunk"]
    assert {p["proposal_id"] for p in additions} >= {
        "LAW21655-ADD-TRANSITION-ARTICLE-18",
        "LAW21717-ADD-TRANSITION-ARTICLE-29",
    }


def test_review_package_marks_every_chunk_pending(tmp_path: Path):
    parsed = tmp_path / "parsed"
    chunks = tmp_path / "chunks"
    review = tmp_path / "review"
    parsed.mkdir()
    chunks.mkdir()
    (parsed / "doc.parsed.json").write_text(json.dumps({
        "document_id": "DOC1", "title": "문서", "file_name": "doc.pdf",
        "file_sha256": "abc", "pages": [{"page_number": 1, "text": "텍스트",
        "ocr_status": "success", "page_type": "content", "char_count": 3}],
        "ocr_summary": {"attempted_pages": 1}
    }), encoding="utf-8")
    (chunks / "doc.chunks.json").write_text(json.dumps({
        "document_id": "DOC1", "chunks": [{"chunk_id": "c1", "document_id": "DOC1",
        "text": "민원대응팀 7일 이내", "source_type": "manual", "locator": "p1"}]
    }), encoding="utf-8")
    result = build_review_package(parsed, chunks, review)
    assert result["review_queue_count"] == 2
    queue = (review / "human_review_queue.jsonl").read_text(encoding="utf-8")
    assert '"review_status": "pending"' in queue


def test_apply_requires_explicit_human_approval(tmp_path: Path):
    chunks = tmp_path / "chunks"
    review = tmp_path / "review"
    chunks.mkdir()
    review.mkdir()
    with pytest.raises(ValueError, match="승인된 오버라이드"):
        apply_approved_overrides(chunks, review)
