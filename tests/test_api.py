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
