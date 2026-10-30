from agent import classify


def test_classifier_falls_back_and_exposes_reason(monkeypatch):
    monkeypatch.setattr(
        classify,
        "chat_json",
        lambda **kwargs: (_ for _ in ()).throw(classify.LLMUnavailable("off")),
    )
    result = classify.classify_complaint("다음 주 현장체험학습 준비물과 집결 시간이 언제인가요?")
    assert result["classifier_mode"] == "RULE_FALLBACK"
    assert result["nature"] == "INFO_REQUEST"
    assert "LLMUnavailable" in result["classifier_error"]


def test_classifier_accepts_structured_llm_result(monkeypatch):
    monkeypatch.setattr(classify, "chat_json", lambda **kwargs: {
        "category": "EDU",
        "subcategory": "생활지도 불만",
        "dept": "교육·학생생활",
        "stage": 2,
        "stage_reason": "사실확인 필요",
        "urgency": "MID",
        "urgency_reason": "긴급 안전 신호 없음",
        "is_informational": False,
        "infringement_flags": [],
        "infringement_evidence": [],
        "emotion": "UPSET",
        "language": "ko",
        "summary_for_teacher": "생활지도 관련 불만",
        "action_for_teacher": "사실관계만 확인",
        "needs_fact_check": ["지도 경위"],
        "action_items": [],
        "confidence": 0.86,
        "requires_human_review": True,
        "nature": "COMPLAINT",
        "legal_kind": "고충",
        "domain_p55": "생활지도/상담",
        "special_codes": [],
        "classifier_mode": "LLM",
        "classifier_error": ""
    })
    result = classify.classify_complaint("우리 아이만 계속 혼낸다고 합니다.")
    assert result["classifier_mode"] == "LLM"
    assert result["nature"] == "COMPLAINT"
    assert result["confidence"] == 0.86
    assert result["classifier_error"] == ""


def test_child_abuse_report_mention_not_auto_threat(monkeypatch):
    monkeypatch.setattr(
        classify,
        "chat_json",
        lambda **kwargs: (_ for _ in ()).throw(classify.LLMUnavailable("off")),
    )
    result = classify.classify_complaint("생활지도가 부당하면 아동학대로 신고하겠습니다.")
    assert "CHILD_ABUSE_REPORT_MENTION" in result["special_codes"]
    assert "VERBAL_ABUSE_REVIEW" not in result["special_codes"]
