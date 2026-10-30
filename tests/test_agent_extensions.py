from agent.history_agent import build_history_review
from agent.report_agent import build_support_report


def test_history_review_prioritizes_unanswered_case():
    current = {"id": "C3"}
    related = [
        {"id": "C1", "similarity": 0.9, "status": "IN_PROGRESS", "has_response": False},
        {"id": "C2", "similarity": 0.8, "status": "CLOSED", "has_response": True},
    ]
    result = build_history_review(current, related)
    assert result["repeat_candidate"] is False
    assert result["unanswered_count"] == 1
    assert "미응답" in result["reason"]


def test_support_report_is_draft_not_sent():
    snapshot = {
        "case": {
            "id": "C1",
            "received_at": "2026-10-31T00:00:00+00:00",
            "channel": "web",
            "student_ref": "학생A",
            "raw_text": "민원",
            "status": "IN_PROGRESS",
            "owner_role": "complaint_response_team",
        },
        "tasks": [],
        "events": [],
        "support_requests": [],
    }
    report = build_support_report(snapshot)
    assert report["report_status"] == "DRAFT"
    assert "자동 제출" in report["notice"]
