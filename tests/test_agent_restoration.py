from agent.history_agent import compare_case_text, build_history_review, find_related_cases_from_rows
from agent.validator import validate_response
from agent.multilingual import detect_language_hint
from agent.report_agent import build_support_report

def test_history_adapter_preserves_followup_logic():
    rows = [{"case_id":"old","raw_text":"10월 30일 생활지도 상황을 설명해 주세요",
             "status":"CLOSED","has_substantive_response":True}]
    related = find_related_cases_from_rows(
        raw_text="10월 31일 생활지도 상황을 설명하고 면담해 주세요", rows=rows)
    assert related
    review = build_history_review({"id":"new","raw_text":"x"}, related)
    assert review["history_action"] in {"REVIEW_FOLLOW_UP","REVIEW_REPEAT"}

def test_unanswered_history_is_linked_not_auto_repeated():
    rows = [{"case_id":"old","raw_text":"생활지도 상황을 설명해 주세요",
             "status":"OPEN","has_substantive_response":False}]
    related = find_related_cases_from_rows(raw_text="생활지도 상황을 설명해 주세요", rows=rows)
    review = build_history_review({"id":"new","raw_text":"x"}, related)
    assert review["history_action"] == "LINK_UNRESOLVED"
    assert review["repeat_candidate"] is False

def test_validator_is_deterministic_and_never_auto_sends():
    result = validate_response(draft="학교의 책임을 인정합니다.", evidence=[], classification={})
    assert result["passed"] is False
    assert result["auto_send_allowed"] is False
    assert result["human_review_required"] is True

def test_language_detection_restored():
    assert detect_language_hint("Please explain what happened in class.") == "en"

def test_support_report_accepts_integrated_b_shape():
    report = build_support_report({
        "case":{"id":"c","status":"OPEN","owner_id":"admin","title":"민원"},
        "tasks":[{"type":"FACT_CHECK","assignee_id":"teacher","status":"COMPLETED","reply":"확인"}],
        "events":[{"created_at":"2026-10-31","action":"TASK_UPDATED","actor_id":"teacher"}],
        "support_requests":[],
    })
    assert report["report_status"] == "DRAFT"
    assert "자동 제출" in report["notice"]

def test_support_report_handles_pending_b_task_shape():
    report = build_support_report({
        "case":{"id":"c","status":"OPEN","owner_id":"admin","title":"민원"},
        "tasks":[{"type":"FACT_CHECK","assignee_id":"teacher","status":"REQUESTED","question":"확인"}],
        "events":[],"support_requests":[],
    })
    assert report["pending_work"][0]["task_type"] == "FACT_CHECK"
    assert report["pending_work"][0]["assignee_role"] == "teacher"
