import sqlite3
from pathlib import Path
import pytest
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient
from backend.commands import mutate
from backend.db import Database
from backend.main import create_app
from backend.migration import migrate
from backend.models import Command
from backend.seed import seed


def auth(tokens, user="admin", key="foundation"):
    return {"Authorization": f"Bearer {tokens[user]}", "Idempotency-Key": key}


def test_adopts_legacy_database_without_losing_data(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    db = sqlite3.connect(path)
    db.executescript(Path("backend/schema.sql").read_text(encoding="utf-8"))
    db.execute("INSERT INTO memberships VALUES ('owner','school','ADMIN',1)")
    db.execute("INSERT INTO cases VALUES ('existing','school','보존 사건','owner','OPEN',7)")
    db.commit()
    db.close()
    database = Database(path)
    Database(path)
    with database.transaction() as db:
        assert db.execute("SELECT title, version FROM cases").fetchone()[:] == ("보존 사건", 7)
        assert db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 2
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_failed_migration_rolls_back_schema_and_ledger(tmp_path):
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "001.sql").write_text("CREATE TABLE retained(id INTEGER);\n", encoding="utf-8")
    path = tmp_path / "db.sqlite3"
    migrate(path, directory)
    (directory / "002.sql").write_text("CREATE TABLE rolled_back(id INTEGER);\nINVALID SQL;\n", encoding="utf-8")
    with pytest.raises(sqlite3.OperationalError):
        migrate(path, directory)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='rolled_back'").fetchone() is None
        assert db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1
    (directory / "001.sql").write_text("CREATE TABLE retained(id TEXT);\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed"):
        migrate(path, directory)


def test_missing_or_out_of_order_migration_is_rejected(tmp_path):
    directory = tmp_path / "migrations"
    directory.mkdir()
    file = directory / "002.sql"
    file.write_text("CREATE TABLE original(id INTEGER);\n", encoding="utf-8")
    path = tmp_path / "db.sqlite3"
    migrate(path, directory)
    (directory / "001.sql").write_text("CREATE TABLE earlier(id INTEGER);\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Out-of-order"):
        migrate(path, directory)
    file.unlink()
    with pytest.raises(RuntimeError, match="missing"):
        migrate(path, directory)


@pytest.mark.parametrize("unsafe", ["COMMIT;", "PRAGMA foreign_keys=OFF;", "ATTACH DATABASE ':memory:' AS other;", "SAVEPOINT escape;"])
def test_migration_cannot_escape_atomic_boundary(tmp_path, unsafe):
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "001.sql").write_text("CREATE TABLE forbidden(id INTEGER);\n" + unsafe + "\n", encoding="utf-8")
    path = tmp_path / "db.sqlite3"
    with pytest.raises(sqlite3.DatabaseError):
        migrate(path, directory)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='forbidden'").fetchone() is None


def test_feature_router_uses_shared_commands_and_closure_guard(tmp_path):
    path = tmp_path / "shared.sqlite3"
    tokens = seed(path)["tokens"]
    router = APIRouter()

    @router.post("/api/cases/{case_id}/test-feature")
    def extension(case_id: str, body: Command, request: Request):
        def operation(db, actor, case):
            db.execute("UPDATE cases SET title='확장 완료' WHERE id=?", (case_id,))
            return {"title": "확장 완료"}
        return mutate(request, case_id, body, "TEST_EXTENSION", operation)

    def guard(db, actor, case_id):
        assert db.in_transaction
        if db.execute("SELECT title FROM cases WHERE id=?", (case_id,)).fetchone()[0] == "확장 완료":
            return [{"code": "RESPONSE_NOT_DELIVERED", "resource_type": "response", "resource_id": "r1", "message": "답변 전달 필요"}]
        return []

    with TestClient(create_app(path, feature_routers=[router], closure_guards=[guard])) as client:
        response = client.post("/api/cases/demo-case/test-feature", headers=auth(tokens), json={"expected_version": 1})
        assert response.status_code == 200 and response.json()["version"] == 2
        repeated = client.post("/api/cases/demo-case/test-feature", headers=auth(tokens), json={"expected_version": 1})
        assert repeated.json() == response.json()
        response = client.post("/api/cases/demo-case/close", headers=auth(tokens, key="close"), json={"expected_version": 2, "reason": "검토"})
        assert response.status_code == 409
        assert response.json()["blockers"][0]["code"] == "RESPONSE_NOT_DELIVERED"
        record = client.get("/api/cases/demo-case", headers=auth(tokens)).json()
        assert record["status"] == "OPEN" and record["version"] == 2
        timeline = client.get("/api/cases/demo-case/timeline", headers=auth(tokens)).json()
        assert len(timeline) == 2 and timeline[-1]["action"] == "TEST_EXTENSION"


def test_guard_failure_rolls_back_and_does_not_close(tmp_path):
    path = tmp_path / "guard.sqlite3"
    tokens = seed(path)["tokens"]
    def guard(db, actor, case_id):
        db.execute("UPDATE cases SET title='must rollback' WHERE id=?", (case_id,))
        raise RuntimeError("guard unavailable")
    with TestClient(create_app(path, closure_guards=[guard]), raise_server_exceptions=False) as client:
        response = client.post("/api/cases/demo-case/close", headers=auth(tokens), json={"expected_version": 1, "reason": "검토"})
        assert response.status_code == 500
        case = client.get("/api/cases/demo-case", headers=auth(tokens)).json()
        assert case["version"] == 1 and case["status"] == "OPEN" and case["title"] != "must rollback"


def test_queues_and_members_respect_scope_and_pagination(tmp_path):
    path = tmp_path / "queues.sqlite3"
    tokens = seed(path)["tokens"]
    app = create_app(path)
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO cases VALUES ('z-case','demo-school','두 번째','admin','OPEN',1)")
    with TestClient(app) as client:
        first = client.get("/api/cases?limit=1", headers=auth(tokens)).json()
        assert first["items"][0]["id"] == "demo-case" and first["next_cursor"] == "demo-case"
        second = client.get("/api/cases?limit=1&after=demo-case", headers=auth(tokens)).json()
        assert second["items"][0]["id"] == "z-case" and second["next_cursor"] is None
        for user in ["outsider", "other-admin", "teacher"]:
            assert client.get("/api/cases", headers=auth(tokens, user)).json()["items"] == []
        assert client.get("/api/cases/demo-case/members", headers=auth(tokens, "teacher")).status_code == 403
        client.post("/api/cases/demo-case/tasks", headers=auth(tokens), json={"expected_version": 1, "type": "FACT_CHECK", "assignee_id": "teacher", "question": "확인"})
        tasks = client.get("/api/my/tasks", headers=auth(tokens, "teacher")).json()["items"]
        assert len(tasks) == 1 and tasks[0]["case_version"] == 2
        assert client.get("/api/my/tasks", headers=auth(tokens)).json()["items"] == []
        members = client.get("/api/cases/demo-case/members", headers=auth(tokens, "teacher")).json()
        assert {m["user_id"] for m in members} == {"admin", "deputy", "teacher"}
        assert all(set(m) == {"user_id", "role"} for m in members)
        assert client.get("/api/cases/demo-case/members", headers=auth(tokens, "other-admin")).status_code == 404
        with app.state.db.transaction() as db:
            db.execute("DELETE FROM case_participants WHERE user_id='teacher'")
        assert client.get("/api/my/tasks", headers=auth(tokens, "teacher")).json()["items"] == []
