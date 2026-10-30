from agent.pipeline import process
from agent.draft import draft_information_reply
from agent import knowledge


def test_pipeline_returns_required_sections():
    result = process({"text": "다음 주 현장체험학습 준비물과 집결 시간이 언제인가요?"})
    assert {"classification", "routing", "evidence", "response_draft", "teacher_card"} <= set(result)
    assert result["requires_human_review"] is True


def test_empty_text_raises():
    try:
        process({"text": " "})
    except ValueError:
        return
    raise AssertionError("Expected ValueError")


def test_draft_supports_new_retrieval_metadata_schema():
    text = draft_information_reply("문의", [{
        "title": "학교민원 처리 매뉴얼",
        "pdf_page": 15,
        "chunk_id": "abc123",
    }])
    assert "p.15" in text
    assert "abc123" in text


def test_draft_supports_legacy_evidence_schema():
    text = draft_information_reply("문의", [{
        "title": "학교민원 처리 매뉴얼",
        "page": 10,
        "id": "legacy-1",
    }])
    assert "p.10" in text
    assert "legacy-1" in text


def test_knowledge_wrapper_forwards_allowed_source_types(monkeypatch):
    captured = {}

    def fake_retrieve(query, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(knowledge, "_retrieve", fake_retrieve)
    knowledge.retrieve("질문", allowed_source_types={"school_policy"})
    assert captured["allowed_source_types"] == {"school_policy"}
