from agent.pipeline import process


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
