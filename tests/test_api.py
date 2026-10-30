from fastapi.testclient import TestClient

import backend.main as backend_main


def test_health_endpoint():
    client = TestClient(backend_main.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_case_endpoint(monkeypatch):
    fake = {
        "case": {"id": "CASE-TEST"},
        "tasks": [],
        "events": [],
        "support_requests": [],
    }
    monkeypatch.setattr(backend_main, "create_case", lambda complaint: fake)
    client = TestClient(backend_main.app)
    response = client.post("/cases", json={
        "text": "우리 아이만 계속 혼난다고 합니다.",
        "channel": "web",
        "complainant_id": "P1",
        "student_ref": "S1",
    })
    assert response.status_code == 201
    assert response.json()["case"]["id"] == "CASE-TEST"


def test_complete_task_rejects_task_from_other_case(monkeypatch):
    monkeypatch.setattr(
        backend_main,
        "get_case_snapshot",
        lambda case_id: {
            "case": {"id": case_id},
            "tasks": [{"id": "TASK-OTHER"}],
            "events": [],
            "support_requests": [],
        },
    )
    client = TestClient(backend_main.app)
    response = client.post(
        "/cases/CASE-1/tasks/TASK-NOT-MINE/complete",
        json={"result_text": "확인했습니다.", "actor": "homeroom_teacher"},
    )
    assert response.status_code == 404



def test_explanation_endpoint(monkeypatch):
    fake = {
        "case_id": "CASE-1",
        "judgment": {"category": "생활지도/상담", "urgency": "LOW", "why": ["사실 확인 요청"]},
        "facts": {"confirmed": [], "needs_confirmation": [], "human_review": []},
        "official_basis": [],
        "history": {"status": "NONE", "label": "반복 이력 특이사항 없음"},
        "safety": {"human_review_required": True, "auto_send": False},
    }
    monkeypatch.setattr(backend_main, "get_case_explanation", lambda case_id: fake)
    client = TestClient(backend_main.app)
    response = client.get("/cases/CASE-1/explanation")
    assert response.status_code == 200
    assert response.json()["safety"]["auto_send"] is False



def test_delivery_endpoint(monkeypatch):
    fake = {
        "case": {"id": "CASE-1", "status": "RESOLVED"},
        "tasks": [],
        "events": [],
        "support_requests": [],
    }
    monkeypatch.setattr(backend_main, "deliver_response", lambda case_id, actor, channel, note: fake)
    client = TestClient(backend_main.app)
    response = client.post("/cases/CASE-1/deliver", json={
        "actor": "complaint_response_team",
        "channel": "web",
        "note": "전달 완료",
    })
    assert response.status_code == 200
    assert response.json()["case"]["status"] == "RESOLVED"


def test_dashboard_endpoint(monkeypatch):
    monkeypatch.setattr(backend_main, "dashboard_metrics", lambda: {
        "total_cases": 3,
        "open_cases": 1,
        "resolved_cases": 2,
        "average_processing_hours": 4.5,
        "related_history_rate": 0.33,
        "overdue_task_count": 0,
        "type_counts": {},
        "open_task_load": [],
        "metric_note": "test",
    })
    client = TestClient(backend_main.app)
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    assert response.json()["total_cases"] == 3
