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
