import json
from pathlib import Path

from agent import retrieval


def test_char_bigram_retrieval_prefers_relevant_text(monkeypatch):
    monkeypatch.setattr(retrieval, "load_corpus", lambda **kwargs: [
        {
            "chunk_id": "a", "source_id": "M", "title": "학교민원 처리 매뉴얼",
            "source_type": "official_manual", "authority_rank": 4,
            "text": "복합민원 처리 기한은 7일 이내", "locator": "p15",
            "verification_status": "verified",
        },
        {
            "chunk_id": "b", "source_id": "P", "title": "정책자료",
            "source_type": "policy_plan", "authority_rank": 6,
            "text": "교육활동 보호 정책 추진 배경", "locator": "p1",
            "verification_status": "verified",
        },
    ])
    results = retrieval.retrieve("복합민원 처리기한", top_k=2)
    assert results[0]["chunk_id"] == "a"


def test_production_excludes_pending(tmp_path: Path, monkeypatch):
    chunks = tmp_path / "chunks"
    corrected = tmp_path / "corrected"
    chunks.mkdir()
    corrected.mkdir()
    (chunks / "x.json").write_text(json.dumps({
        "chunks": [
            {"chunk_id": "pending", "document_id": "MOE-MANUAL-2026",
             "source_type": "official_manual", "text": "내용", "locator": "p15",
             "verification_status": "pending"},
            {"chunk_id": "ok", "document_id": "MOE-MANUAL-2026",
             "source_type": "official_manual", "text": "내용", "locator": "p15",
             "verification_status": "verified"},
        ]
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(retrieval, "CHUNKS_DIR", chunks)
    monkeypatch.setattr(retrieval, "CORRECTED_DIR", corrected)
    monkeypatch.setattr(retrieval, "_registry", lambda: {})
    monkeypatch.setattr(retrieval, "_allowlist", lambda: {"sources": {}})
    corpus = retrieval.load_corpus(production=True, as_of_date="2026-10-30")
    assert [x["chunk_id"] for x in corpus] == ["ok"]


def test_scheduled_law_filtered_by_date(tmp_path: Path, monkeypatch):
    chunks = tmp_path / "chunks"
    corrected = tmp_path / "corrected"
    chunks.mkdir()
    corrected.mkdir()
    (chunks / "law.json").write_text(json.dumps({
        "chunks": [{
            "chunk_id": "law", "document_id": "LAW-X", "source_type": "law",
            "text": "개정 조문", "locator": "제1조@scheduled",
            "version_status": "scheduled", "effective_from": "2026-12-03",
            "verification_status": "verified"
        }]
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(retrieval, "CHUNKS_DIR", chunks)
    monkeypatch.setattr(retrieval, "CORRECTED_DIR", corrected)
    monkeypatch.setattr(retrieval, "_registry", lambda: {})
    monkeypatch.setattr(retrieval, "_allowlist", lambda: {"sources": {}})
    assert retrieval.load_corpus(production=True, as_of_date="2026-10-30") == []
    assert len(retrieval.load_corpus(production=True, as_of_date="2026-12-03")) == 1


def test_criteria_contract_separates_manual_and_legal_due():
    path = retrieval.CONTRACTS_DIR / "criteria_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["handling_level"]["COOP"]["manual_due"]["authority"] == "manual_proposal"
    assert payload["legal_due_rules"]["QUESTION_SYSTEM_OR_PROCEDURE"]["authority"] == "legal"
