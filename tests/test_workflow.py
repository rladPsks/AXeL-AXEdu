from pathlib import Path

import db
from agent.action_router import decide_actions
from agent import workflow


def test_action_router_creates_fact_check_for_life_guidance():
    actions = decide_actions(
        {
            "nature": "COMPLAINT",
            "domain_p55": "생활지도/상담",
            "urgency": "LOW",
            "special_codes": [],
            "infringement_flags": [],
            "needs_fact_check": ["지도 시점", "지도 사유"],
            "repeat_review": False,
        },
        {"action_role": "homeroom_teacher", "approver": "vice_principal"},
        [],
    )
    assert actions[0]["task_type"] == "FACT_CHECK"
    assert actions[0]["assignee_role"] == "homeroom_teacher"


def test_action_router_info_without_school_evidence_requests_fact_check():
    actions = decide_actions(
        {
            "nature": "INFO_REQUEST",
            "domain_p55": "교무/학사",
            "urgency": "LOW",
            "special_codes": [],
            "infringement_flags": [],
            "repeat_review": False,
        },
        {"suggested_owner": "complaint_response_team"},
        [],
    )
    assert actions[0]["task_type"] == "FACT_CHECK"
    assert actions[0]["assignee_role"] == "school_information_owner"


def test_workflow_persists_case_task_and_event(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "workflow.sqlite3")
    monkeypatch.setattr(workflow, "init_db", db.init_db)

    fake = {
        "classification": {
            "nature": "COMPLAINT",
            "domain_p55": "생활지도/상담",
            "urgency": "LOW",
            "special_codes": [],
            "infringement_flags": [],
            "needs_fact_check": ["지도 시점"],
            "repeat_review": False,
            "classifier_mode": "LLM",
        },
        "routing": {
            "suggested_owner": "complaint_response_team",
            "action_role": "homeroom_teacher",
            "approver": "vice_principal",
        },
        "evidence": [],
        "response_draft": "검토 필요",
    }
    monkeypatch.setattr(workflow, "process", lambda complaint, history=None: fake)

    snapshot = workflow.create_case(
        {"text": "우리 아이만 계속 혼난다고 합니다.", "channel": "web"},
        case_id="CASE-TEST",
    )
    assert snapshot["case"]["status"] == "IN_PROGRESS"
    assert snapshot["case"]["next_action"] == "FACT_CHECK"
    assert snapshot["tasks"][0]["task_type"] == "FACT_CHECK"
    assert any(e["event_type"] == "AI_TRIAGE_COMPLETED" for e in snapshot["events"])


def test_rules_accept_timezone_aware_history():
    from agent.rules import apply_rules
    out = apply_rules(
        {"urgency": "LOW", "stage": 2, "infringement_flags": []},
        [{"received_at": "2026-10-30T16:14:16.131341+00:00", "status": "IN_PROGRESS"}],
    )
    assert out["repeat_count"] == 2
    assert out["repeat_review"] is False


def test_info_policy_question_allows_official_sources():
    from agent.pipeline import _allowed_source_types
    cls = {"nature": "INFO_REQUEST"}
    assert _allowed_source_types(cls, "교육활동 침해가 발생하면 학교는 어떤 조치를 해야 하나요?") == {"law", "decree", "official_manual", "local_rule", "policy_plan"}
    assert _allowed_source_types(cls, "내일 체험학습 몇 시까지 등교하나요?") == {"school_policy"}


def test_history_draft_is_not_substantive_response():
    from agent.history_agent import build_history_review
    review = build_history_review(
        {"id": "CURRENT"},
        [{
            "id": "OLD",
            "similarity": 1.0,
            "status": "IN_PROGRESS",
            "response_status": "DRAFTED",
            "has_substantive_response": False,
        }],
    )
    assert review["repeat_candidate"] is False
    assert review["unanswered_count"] == 1


def test_history_review_same_answered_request_is_repeat_candidate():
    from agent.history_agent import build_history_review
    review = build_history_review(
        {"id": "CURRENT", "raw_text": "우리 아이만 계속 혼낸다고 합니다. 확인해주세요."},
        [{
            "id": "OLD",
            "raw_text": "우리 아이만 계속 혼낸다고 합니다. 확인해주세요.",
            "similarity": 1.0,
            "status": "RESOLVED",
            "response_status": "DELIVERED",
            "has_substantive_response": True,
            "comparison": {
                "similarity": 1.0,
                "has_new_information": False,
                "new_terms": [],
                "new_numbers": [],
                "new_dates": [],
                "new_requests": [],
            },
        }],
    )
    assert review["repeat_candidate"] is True
    assert review["follow_up_candidate"] is False
    assert review["history_action"] == "REVIEW_REPEAT"


def test_history_review_new_date_or_request_is_follow_up_not_repeat():
    from agent.history_agent import build_history_review, compare_case_text
    old = "아이 생활지도 상황을 확인해주세요."
    current = "지난주 10월 29일에도 같은 일이 있었습니다. 관리자 면담도 요청합니다."
    comparison = compare_case_text(current, old)
    review = build_history_review(
        {"id": "CURRENT", "raw_text": current},
        [{
            "id": "OLD",
            "raw_text": old,
            "similarity": 0.65,
            "status": "RESOLVED",
            "response_status": "DELIVERED",
            "has_substantive_response": True,
            "comparison": comparison,
        }],
    )
    assert comparison["has_new_information"] is True
    assert review["repeat_candidate"] is False
    assert review["follow_up_candidate"] is True
    assert review["history_action"] == "REVIEW_FOLLOW_UP"


def test_history_review_unanswered_related_case_links_without_repeat():
    from agent.history_agent import build_history_review
    review = build_history_review(
        {"id": "CURRENT", "raw_text": "같은 내용입니다."},
        [{
            "id": "OLD",
            "raw_text": "같은 내용입니다.",
            "similarity": 1.0,
            "status": "IN_PROGRESS",
            "response_status": "DRAFTED",
            "has_substantive_response": False,
            "comparison": {"similarity": 1.0, "has_new_information": False},
        }],
    )
    assert review["repeat_candidate"] is False
    assert review["history_action"] == "LINK_UNRESOLVED"


def test_action_router_creates_history_task_for_follow_up():
    actions = decide_actions(
        {
            "nature": "COMPLAINT",
            "domain_p55": "생활지도/상담",
            "urgency": "LOW",
            "special_codes": [],
            "infringement_flags": [],
            "needs_fact_check": [],
            "repeat_review": False,
            "history_review_required": True,
            "history_action": "REVIEW_FOLLOW_UP",
        },
        {"action_role": "homeroom_teacher", "approver": "vice_principal"},
        [],
    )
    history = [x for x in actions if x["task_type"] == "HISTORY_REVIEW"]
    assert len(history) == 1
    assert "후속 민원" in history[0]["reason"]
