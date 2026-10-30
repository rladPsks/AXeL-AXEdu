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


def test_registry_alias_maps_to_canonical_source(monkeypatch):
    registry = {
        "학교 민원 응대 안내자료": {
            "source_id": "MOE-GYEONGGI-COMPLAINT-GUIDE-2024",
            "title": "학교 민원 응대 안내자료",
            "source_type": "legacy_operational_guidance",
        }
    }
    item = retrieval._normalize_chunk({
        "chunk_id": "x",
        "document_id": "학교 민원 응대 안내자료",
        "text": "폭언 시 통화 종료",
        "locator": "p20",
    }, registry)
    assert item["source_id"] == "MOE-GYEONGGI-COMPLAINT-GUIDE-2024"
    assert item["document_id"] == "MOE-GYEONGGI-COMPLAINT-GUIDE-2024"


def test_allowed_source_types_filters_information_sources(monkeypatch):
    monkeypatch.setattr(retrieval, "load_corpus", lambda **kwargs: [
        {
            "chunk_id": "school", "source_id": "S", "title": "학교 일정",
            "source_type": "school_policy", "authority_rank": 5,
            "text": "현장체험학습 집결 시간은 오전 8시", "locator": "p1",
            "verification_status": "verified",
        }
    ] if kwargs.get("allowed_source_types") == {"school_policy"} else [])
    results = retrieval.retrieve(
        "현장체험학습 집결 시간",
        allowed_source_types={"school_policy"},
    )
    assert results[0]["chunk_id"] == "school"


def test_legacy_guidance_does_not_dominate_results(monkeypatch):
    monkeypatch.setattr(retrieval, "load_corpus", lambda **kwargs: [
        {
            "chunk_id": "law", "source_id": "LAW", "title": "교원지위법",
            "source_type": "law", "authority_rank": 1,
            "text": "교육활동 침해 발생 시 피해교원 보호조치와 침해자 조치 절차",
            "locator": "제18조", "verification_status": "verified",
        },
        {
            "chunk_id": "manual", "source_id": "MANUAL", "title": "학교민원 처리 매뉴얼",
            "source_type": "official_manual", "authority_rank": 4,
            "text": "교육활동 침해 사안은 관리자 검토와 보호조치를 연계한다",
            "locator": "p20", "verification_status": "verified",
        },
        {
            "chunk_id": "legacy1", "source_id": "LEGACY", "title": "학교 민원 응대 안내자료",
            "source_type": "legacy_operational_guidance", "authority_rank": 6,
            "text": "교육활동 침해 시 폭언 응대 조치",
            "locator": "p20", "verification_status": "pending",
        },
        {
            "chunk_id": "legacy2", "source_id": "LEGACY", "title": "학교 민원 응대 안내자료",
            "source_type": "legacy_operational_guidance", "authority_rank": 6,
            "text": "교육활동 침해 시 관리자 조치",
            "locator": "p21", "verification_status": "pending",
        },
    ])
    results = retrieval.retrieve("교육활동 침해 조치", top_k=4)
    assert results[0]["source_type"] in {"law", "official_manual"}
    assert sum(r["source_id"] == "LEGACY" for r in results) <= 1
