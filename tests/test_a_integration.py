from fastapi.testclient import TestClient

from backend.main import create_app
from backend.seed import seed
import backend.features.intake as intake_feature


def auth(tokens, user="admin", key="intake"):
    return {
        "Authorization": f"Bearer {tokens[user]}",
        "Idempotency-Key": key,
    }


def test_integrated_intake_creates_shared_case_and_routed_tasks(monkeypatch, tmp_path):
    path = tmp_path / "integration.sqlite3"
    tokens = seed(path)["tokens"]

    monkeypatch.setattr(
        intake_feature,
        "classify_complaint",
        lambda text: {
            "category": "EDU",
            "nature": "COMPLAINT",
            "domain_p55": "생활지도/상담",
            "urgency": "LOW",
            "stage": 2,
            "is_informational": False,
            "needs_fact_check": ["수업 당시 지도 상황 확인", "다른 학생과 동일 기준인지 확인"],
            "special_codes": [],
            "infringement_flags": [],
            "summary_for_teacher": "생활지도 상황과 지도 기준 확인 요청",
            "classifier_mode": "TEST",
        },
    )

    with TestClient(create_app(path)) as client:
        response = client.post(
            "/api/intakes",
            headers=auth(tokens),
            json={
                "channel": "phone",
                "complainant_name": "가상보호자",
                "student_name": "가상학생",
                "complaint_type": "생활지도 불만",
                "raw_text": "우리 아이만 자주 혼나는 것 같아 지도 상황을 확인해 주세요.",
                "related_people": [],
                "incident_context": "전화 접수",
                "occurred_at": "2026-10-30T09:30:00+09:00",
            },
        )
        assert response.status_code == 201
        result = response.json()
        case_id = result["case_id"]
        assert result["classification"]["handling_route"] == "STAFF_OR_TEAM"
        assert result["routing"]["duty_label"] == "생활지도·학생 갈등"

        case = client.get(f"/api/cases/{case_id}", headers=auth(tokens)).json()
        assert case["id"] == case_id
        assert case["owner_id"] == "deputy"
        assert {task["assignee_id"] for task in case["tasks"]} == {"deputy"}
        assert all(task["type"] == "FACT_CHECK" for task in case["tasks"])

        intake = client.get(f"/api/cases/{case_id}/intake", headers=auth(tokens)).json()
        assert intake["raw_text"].startswith("우리 아이만")
        assert intake["occurred_at"] == "2026-10-30T00:30:00+00:00"
        assert intake["received_at"] != intake["occurred_at"]
        listing = client.get("/api/cases", headers=auth(tokens)).json()["items"]
        summary = next(c for c in listing if c["id"] == case_id)
        assert summary["stage"] == "review"
        assert summary["channel"] == "phone"
        assert "classification_json" not in summary
        assert intake["classification"]["core_demand"] == "생활지도 상황과 지도 기준 확인 요청"
        assert intake["routing"]["approver"] == "VICE_PRINCIPAL"
        assert intake["workflow"]["agent"]["orchestrator"] == "AXeL"
        assert "rag" in intake["workflow"]["tools"]
        assert "history" in intake["workflow"]["tools"]
        assert intake["workflow"]["action_plan"]["case_owner"] == "deputy"

        brief_path = f"/api/cases/{case_id}/teacher-brief"
        brief = {"expected_version": 1, "summary": "관리자가 확인한 요약", "action": "지도 기록을 확인해 주세요."}
        assert client.post(brief_path, headers=auth(tokens, "teacher", "brief-denied"), json=brief).status_code == 403
        assert client.post(brief_path, headers=auth(tokens, "other-admin", "brief-cross-school"), json=brief).status_code == 404
        saved = client.post(brief_path, headers=auth(tokens, key="brief-save"), json=brief)
        assert saved.status_code == 200
        assert saved.json()["version"] == 2
        assert client.post(brief_path, headers=auth(tokens, key="brief-save"), json=brief).json() == saved.json()
        assert client.post(brief_path, headers=auth(tokens, key="brief-stale"), json=brief).status_code == 409
        updated = client.get(f"/api/cases/{case_id}/intake", headers=auth(tokens)).json()
        assert updated["workflow"]["teacher_card"]["summary"] == brief["summary"]
        assert updated["workflow"]["teacher_card"]["action"] == brief["action"]
        assert updated["raw_text"] == intake["raw_text"]

        repeated = client.post(
            "/api/intakes",
            headers=auth(tokens),
            json={
                "channel": "phone",
                "complainant_name": "가상보호자",
                "student_name": "가상학생",
                "complaint_type": "생활지도 불만",
                "raw_text": "우리 아이만 자주 혼나는 것 같아 지도 상황을 확인해 주세요.",
                "related_people": [],
                "incident_context": "전화 접수",
                "occurred_at": "2026-10-30T09:30:00+09:00",
            },
        )
        assert repeated.status_code == 201
        assert repeated.json()["case_id"] == case_id

        # Teachers see only their own connected complaints; administrators see the school list.
        def listed(user):
            return {item["id"] for item in client.get("/api/cases", headers=auth(tokens, user)).json()["items"]}
        assert listed("teacher") == set()
        assert listed("outsider") == set()
        assert listed("admin") == {"demo-case", case_id}
        assert listed("deputy") == {"demo-case", case_id}
        assert listed("other-admin") == set()

        # The submission reaches the assigned staff and both school administrators once,
        # and never reaches an unrelated teacher or another school.
        from backend.notifications import dispatch_once
        dispatch_once(client.app.state.db)
        for user in ("admin", "deputy"):
            inbox = client.get("/api/notifications", headers=auth(tokens, user)).json()
            arrivals = [n for n in inbox if n["kind"] == "CASE_INTAKE_CREATED"]
            assert len(arrivals) == 1
            assert arrivals[0]["case_id"] == case_id
            assert arrivals[0]["case_title"] == case["title"]
        for user in ("teacher", "outsider", "other-admin"):
            assert client.get("/api/notifications", headers=auth(tokens, user)).json() == []


def test_life_guidance_intake_uses_user_category_for_duty_and_does_not_draft_before_fact_check(monkeypatch, tmp_path):
    from backend.main import create_app
    from backend.seed import seed
    from fastapi.testclient import TestClient
    path = tmp_path / "life-guidance.sqlite3"
    creds = seed(path)
    app = create_app(path, inbox_worker=False)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + creds["tokens"]["admin"], "Idempotency-Key": "life-guidance-intake"}
        response = client.post("/api/intakes", headers=headers, json={
            "channel":"phone","complainant_name":"테스트보호자","student_name":"테스트학생",
            "complaint_type":"생활지도 불만","related_people":["담임교사"],
            "incident_context":"수업 중 생활지도 상황",
            "raw_text":"우리 아이가 다른 학생보다 자주 지적받는다고 합니다. 상황을 확인해 주세요.",
        })
        assert response.status_code == 201
        case_id = response.json()["case_id"]
        detail = client.get(f"/api/cases/{case_id}/intake", headers={"Authorization":"Bearer "+creds["tokens"]["admin"]}).json()
        assert detail["routing"]["duty_area"] == "student_life"
        assert detail["routing"]["action_role"] == "HEAD_LIFE_PE"
        assert detail["workflow"]["initial_response_draft"] == ""
