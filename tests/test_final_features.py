from pathlib import Path

import db
from agent import workflow
from agent.multilingual import detect_language_hint
from agent.pipeline import _derive_handling_route
from agent.validator import validate_response


def _fake_result(status_text: str = "초안"):
    return {
        "classification": {
            "nature": "COMPLAINT",
            "domain_p55": "생활지도/상담",
            "urgency": "LOW",
            "special_codes": [],
            "infringement_flags": [],
            "classifier_mode": "LLM",
            "handling_route": "STAFF_OR_TEAM",
        },
        "routing": {
            "suggested_owner": "complaint_response_team",
            "action_role": "HEAD_LIFE_PE",
            "collaborators": ["HOMEROOM"],
            "approver": "VICE_PRINCIPAL",
            "backup_role": "PRINCIPAL",
            "callback_needed": "UNDECIDED",
            "role_labels": {
                "HEAD_LIFE_PE": "생활체육부장",
                "HOMEROOM": "담임교사",
                "VICE_PRINCIPAL": "교감",
                "PRINCIPAL": "교장",
            },
        },
        "response_draft": status_text,
    }


def test_handling_route_three_way():
    assert _derive_handling_route({
        "nature": "INFO_REQUEST", "urgency": "LOW",
        "special_codes": [], "infringement_flags": []
    }) == "FRONT_DESK_RESOLVE"
    assert _derive_handling_route({
        "nature": "COMPLAINT", "urgency": "LOW",
        "special_codes": [], "infringement_flags": []
    }) == "STAFF_OR_TEAM"
    assert _derive_handling_route({
        "nature": "SAFETY", "urgency": "HIGH",
        "special_codes": [], "infringement_flags": []
    }) == "ADMIN_REVIEW"


def test_multilingual_language_hint():
    assert detect_language_hint("학교 일정이 궁금합니다") == "ko"
    assert detect_language_hint("When does school start tomorrow?") == "en"


def test_validator_blocks_unapproved_promise_and_risky_contact():
    result = validate_response(
        draft="학교의 책임을 인정하며 전화 상담을 진행하겠습니다.",
        evidence=[],
        classification={
            "urgency": "HIGH",
            "special_codes": ["THREAT_REVIEW"],
            "infringement_flags": [],
        },
    )
    codes = {x["code"] for x in result["issues"]}
    assert result["passed"] is False
    assert "UNAUTHORIZED_PROMISE" in codes
    assert "RISKY_DIRECT_CONTACT" in codes
    assert result["auto_send_allowed"] is False


def test_snapshot_exposes_callback_and_backup_labels(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "snapshot.sqlite3")
    monkeypatch.setattr(workflow, "init_db", db.init_db)
    db.init_db()
    result = _fake_result()
    db.create_case_record(
        "CASE-META",
        {"text": "생활지도 확인", "channel": "web"},
        result,
        status="IN_PROGRESS",
        owner_role="complaint_response_team",
        next_action="FACT_CHECK",
    )
    db.create_task_record({
        "id": "TASK-META",
        "case_id": "CASE-META",
        "task_type": "COOP_FACT_CHECK",
        "assignee_role": "HOMEROOM",
        "status": "REQUESTED",
        "reason": "담임 사실 확인",
        "instructions": [],
    })
    snapshot = workflow.get_case_snapshot("CASE-META")
    task = snapshot["tasks"][0]
    assert task["assignee_label"] == "담임교사"
    assert task["backup_label"] == "교장"
    assert task["support_label"] == "교감"
    assert task["callback_needed"] == "UNDECIDED"


def test_delegate_to_team_changes_owner_and_records_event(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "delegate.sqlite3")
    monkeypatch.setattr(workflow, "init_db", db.init_db)
    db.init_db()
    result = _fake_result()
    db.create_case_record(
        "CASE-DELEGATE",
        {"text": "민원", "channel": "web"},
        result,
        status="IN_PROGRESS",
        owner_role="HOMEROOM",
        next_action="FACT_CHECK",
    )
    snapshot = workflow.delegate_case_to_team(
        "CASE-DELEGATE",
        actor="HOMEROOM",
        note="학교 차원의 공동 처리 요청",
    )
    assert snapshot["case"]["owner_role"] == "complaint_response_team"
    assert any(t["task_type"] == "TEAM_REVIEW" for t in snapshot["tasks"])
    assert any(e["event_type"] == "TEACHER_DELEGATED_TO_TEAM" for e in snapshot["events"])


def test_similar_cases_only_returns_resolved_and_hides_identifiers(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "similar.sqlite3")
    monkeypatch.setattr(workflow, "init_db", db.init_db)
    db.init_db()
    result = _fake_result("확인 후 보호자에게 안내했습니다.")
    db.create_case_record(
        "CASE-OLD",
        {
            "text": "우리 아이만 계속 혼난다고 합니다.",
            "channel": "web",
            "complainant_id": "SECRET-PARENT",
            "student_ref": "SECRET-STUDENT",
        },
        result,
        status="RESOLVED",
        owner_role="complaint_response_team",
        next_action="CLOSED",
    )
    db.create_case_record(
        "CASE-NEW",
        {"text": "우리 아이만 계속 혼난다고 합니다.", "channel": "web"},
        result,
        status="IN_PROGRESS",
        owner_role="complaint_response_team",
        next_action="FACT_CHECK",
    )
    found = workflow.get_similar_cases("CASE-NEW", limit=1)["items"]
    assert len(found) == 1
    assert found[0]["case_id"] == "CASE-OLD"
    assert "complainant_id" not in found[0]
    assert "student_ref" not in found[0]
    assert "raw_text" not in found[0]


def test_explanation_read_does_not_append_history_event(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "explain-readonly.sqlite3")
    monkeypatch.setattr(workflow, "init_db", db.init_db)
    db.init_db()
    result = _fake_result()
    db.create_case_record(
        "CASE-E",
        {"text": "우리 아이만 혼난다고 합니다.", "channel": "web"},
        result,
        status="IN_PROGRESS",
        owner_role="complaint_response_team",
        next_action="FACT_CHECK",
    )
    db.save_ai_run("CASE-E", "INITIAL_TRIAGE", {"text": "x"}, {
        "classification": result["classification"],
        "routing": result["routing"],
        "evidence": [],
        "validation": {"passed": True, "issues": []},
    })
    before = len(db.list_case_events("CASE-E"))
    workflow.get_case_explanation("CASE-E")
    after = len(db.list_case_events("CASE-E"))
    assert before == after
