import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.seed import seed


@pytest.fixture
def env(tmp_path):
    path = tmp_path / "test.sqlite3"
    tokens = seed(path)["tokens"]
    app = create_app(path)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, tokens, app.state.db


def headers(tokens, user="admin", key=None):
    return {"Authorization": "Bearer " + tokens[user], "Idempotency-Key": key or str(uuid4())}


def task(client, tokens, version=1, **changes):
    body = {"expected_version": version, "type": "CALLBACK", "assignee_id": "teacher",
            "question": "[가상] 상담 일정을 확인해 주세요.", "callback_needed": "REQUIRED", **changes}
    return client.post("/api/cases/demo-case/tasks", json=body, headers=headers(tokens))


def test_teacher_support_flow_persists_and_keeps_owner(env):
    client, tokens, database = env
    response = task(client, tokens)
    assert response.status_code == 201
    task_id = response.json()["task_id"]
    response = client.patch(f"/api/tasks/{task_id}", headers=headers(tokens, "teacher"),
                            json={"expected_version": 2, "status": "COMPLETED", "reply": "일정 확인 완료"})
    assert response.status_code == 200
    response = client.post("/api/cases/demo-case/support-requests", headers=headers(tokens, "teacher"),
                           json={"expected_version": 3, "coordinator_id": "admin", "type": "ATTEND",
                                 "reason": "동석을 요청합니다."})
    assert response.status_code == 201
    support_id = response.json()["support_request_id"]
    for version, status in [(4, "ACKNOWLEDGED"), (5, "COMPLETED")]:
        response = client.patch(f"/api/support-requests/{support_id}", headers=headers(tokens),
                                json={"expected_version": version, "status": status,
                                      "result": "동석 지원 완료" if status == "COMPLETED" else None})
        assert response.status_code == 200
    with TestClient(create_app(database.path)) as restarted:
        case = restarted.get("/api/cases/demo-case", headers=headers(tokens, "teacher")).json()
        assert case["version"] == 6 and case["owner_id"] == "admin"
        assert case["tasks"][0]["reply"] == "일정 확인 완료"
        assert case["support_requests"][0]["result"] == "동석 지원 완료"
        timeline = restarted.get("/api/cases/demo-case/timeline", headers=headers(tokens)).json()
        assert len(timeline) == 6
        assert [event["new_version"] for event in timeline] == list(range(1, 7))


def test_session_and_case_scope(env):
    client, tokens, _ = env
    assert client.get("/api/cases/demo-case").status_code == 401
    assert client.get("/api/cases/demo-case", headers=headers(tokens, "other-admin")).status_code == 404
    assert client.get("/api/cases/demo-case", headers=headers(tokens, "outsider")).status_code == 403
    assert task(client, tokens).status_code == 201
    assert client.get("/api/cases/demo-case", headers=headers(tokens, "teacher")).status_code == 200
    response = client.post("/api/cases/demo-case/tasks", headers=headers(tokens, "teacher"),
                           json={"expected_version": 2, "type": "FACT_CHECK", "assignee_id": "teacher",
                                 "question": "검증", "role": "ADMIN"})
    assert response.status_code == 422
    assert "input" not in response.json()


def test_expired_and_deactivated_sessions(env):
    client, tokens, database = env
    with database.transaction() as db:
        db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00' WHERE user_id='teacher'")
        db.execute("UPDATE memberships SET active=0 WHERE user_id='deputy'")
    assert client.get("/api/session", headers=headers(tokens, "teacher")).status_code == 401
    assert client.get("/api/session", headers=headers(tokens, "deputy")).status_code == 401


def test_idempotency_replays_and_rejects_different_body(env):
    client, tokens, _ = env
    body = {"expected_version": 1, "type": "FACT_CHECK", "assignee_id": "teacher", "question": "확인"}
    h = headers(tokens, key="retry-key")
    first = client.post("/api/cases/demo-case/tasks", json=body, headers=h)
    repeat = client.post("/api/cases/demo-case/tasks", json=body, headers=h)
    assert first.status_code == repeat.status_code == 201
    assert first.json() == repeat.json()
    conflict = client.post("/api/cases/demo-case/tasks", json={**body, "question": "다름"}, headers=h)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    case = client.get("/api/cases/demo-case", headers=h).json()
    assert case["version"] == 2 and len(case["tasks"]) == 1


def test_stale_version_and_parallel_updates(env):
    client, tokens, _ = env
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: task(client, tokens), range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409]
    conflict = next(r for r in responses if r.status_code == 409)
    assert conflict.json()["current_version"] == 2


def test_handover_requires_acceptance_by_recipient(env):
    client, tokens, _ = env
    response = client.post("/api/cases/demo-case/handovers", headers=headers(tokens),
                           json={"expected_version": 1, "to_owner_id": "deputy", "reason": "부재 대체"})
    assert response.status_code == 201
    assert response.json()["owner_id"] == "admin"
    handover_id = response.json()["handover_id"]
    wrong_actor = client.post(f"/api/handovers/{handover_id}/accept", headers=headers(tokens),
                              json={"expected_version": 2})
    assert wrong_actor.status_code == 403
    response = client.post(f"/api/handovers/{handover_id}/accept", headers=headers(tokens, "deputy"),
                           json={"expected_version": 2})
    assert response.status_code == 200 and response.json()["owner_id"] == "deputy"


def test_close_guards_and_reopen_preserve_history(env):
    client, tokens, _ = env
    task_id = task(client, tokens).json()["task_id"]
    response = client.post("/api/cases/demo-case/close", headers=headers(tokens),
                           json={"expected_version": 2, "reason": "검토"})
    assert response.status_code == 409 and response.json()["pending"]["tasks"] == 1
    assert client.patch(f"/api/tasks/{task_id}", headers=headers(tokens, "teacher"),
                        json={"expected_version": 2, "status": "COMPLETED", "reply": "완료"}).status_code == 200
    response = client.post("/api/cases/demo-case/close", headers=headers(tokens),
                           json={"expected_version": 3, "reason": "업무 완료"})
    assert response.status_code == 200
    assert task(client, tokens, 4).json()["code"] == "CASE_CLOSED"
    response = client.post("/api/cases/demo-case/reopen", headers=headers(tokens),
                           json={"expected_version": 4, "reason": "새 사실 접수"})
    assert response.status_code == 200 and response.json()["version"] == 5
    assert len(client.get("/api/cases/demo-case/timeline", headers=headers(tokens)).json()) == 5


def test_support_cannot_skip_ack_or_change_owner(env):
    client, tokens, _ = env
    task(client, tokens)
    response = client.post("/api/cases/demo-case/support-requests", headers=headers(tokens, "teacher"),
                           json={"expected_version": 2, "coordinator_id": "admin", "type": "TAKEOVER",
                                 "reason": "공동 대응 요청"})
    support_id = response.json()["support_request_id"]
    response = client.patch(f"/api/support-requests/{support_id}", headers=headers(tokens),
                            json={"expected_version": 3, "status": "COMPLETED", "result": "완료"})
    assert response.status_code == 409
    assert client.get("/api/cases/demo-case", headers=headers(tokens)).json()["owner_id"] == "admin"
    response = client.post("/api/cases/demo-case/close", headers=headers(tokens),
                           json={"expected_version": 3, "reason": "검토"})
    assert response.json()["pending"]["support_requests"] == 1


def test_wrong_task_actor_and_invalid_member(env):
    client, tokens, _ = env
    assert task(client, tokens, assignee_id="other-admin").status_code == 422
    assert task(client, tokens, question="   ").status_code == 422
    task_id = task(client, tokens).json()["task_id"]
    response = client.patch(f"/api/tasks/{task_id}", headers=headers(tokens, "deputy"),
                            json={"expected_version": 2, "status": "COMPLETED", "reply": "위장 회신"})
    assert response.status_code == 403
    response = client.patch(f"/api/tasks/{task_id}", headers=headers(tokens, "teacher"),
                            json={"expected_version": 2, "status": "COMPLETED"})
    assert response.status_code == 422


def test_audit_failure_rolls_back_domain_version_and_idempotency(env):
    client, tokens, database = env
    with database.transaction() as db:
        db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_events "
                   "BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    response = task(client, tokens)
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    with database.transaction() as db:
        assert db.execute("SELECT version FROM cases").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM idempotency").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM case_participants").fetchone()[0] == 0


def test_audit_is_append_only(env):
    _, _, database = env
    for query in ("UPDATE audit_events SET action='changed'", "DELETE FROM audit_events"):
        with pytest.raises(sqlite3.IntegrityError):
            with database.transaction() as db:
                db.execute(query)


def test_contract_contains_b_endpoints(env):
    client, _, _ = env
    schema = client.get("/openapi.json").json()
    assert "/api/cases/{case_id}/support-requests" in schema["paths"]
    assert "/api/handovers/{handover_id}/accept" in schema["paths"]
    operation = schema["paths"]["/api/cases/{case_id}/tasks"]["post"]
    assert operation["security"] == [{"Session": []}]
    assert any(p["name"] == "Idempotency-Key" and p["required"] for p in operation["parameters"])
