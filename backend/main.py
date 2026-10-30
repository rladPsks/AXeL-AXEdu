import json
import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from .db import Database, now, uid
from .access import DomainError, fail, authenticate, accessible_case, admin, member, participate
from .commands import mutate, resource_case
from .closure import ClosureRegistry
from .queries import router as query_router
from .files import router as files_router, upload_limit
from .guardians import router as guardians_router
from .agents import router as agents_router
from .runtime import build_registry
from .models import (CaseTransition, Command, HandoverCreate, SupportCreate,
                     SupportUpdate, TaskCreate, TaskUpdate)


def create_app(db_path=None, *, feature_routers=(), closure_guards=(), max_file_bytes=None, agent_registry=None):
    app = FastAPI(title="학교 민원 에이전트 — 개발자 B", version="0.1.0")
    app.state.db = Database(db_path or os.getenv("SCHOOL_AGENT_DB", "data/private/dev.sqlite3"))

    app.state.closure = ClosureRegistry(closure_guards)
    app.state.agent_registry = agent_registry if agent_registry is not None else build_registry()
    app.state.max_file_bytes = upload_limit() if max_file_bytes is None else max_file_bytes
    if app.state.max_file_bytes < 1:
        raise ValueError('max_file_bytes must be positive')
    app.include_router(query_router)
    app.include_router(files_router)
    app.include_router(guardians_router)
    app.include_router(agents_router)
    for router in feature_routers:
        app.include_router(router)

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = uid()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    def error_response(request, status, code, message, **details):
        body = {"code": code, "message": message, "retryable": False,
                "case_id": None, "run_id": None,
                "request_id": request.state.request_id, **details}
        return JSONResponse(body, status_code=status)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return error_response(request, exc.status, exc.code, exc.message, **exc.details)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        # Avoid echoing raw complaint text, credentials, or Pydantic input values.
        return error_response(request, 422, "VALIDATION_ERROR", "입력 항목을 확인하세요.",
                              fields=[list(e["loc"]) for e in exc.errors()])

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        logging.getLogger(__name__).error("request_failed request_id=%s type=%s",
                                         request.state.request_id, type(exc).__name__)
        return error_response(request, 500, "INTERNAL_ERROR", "처리에 실패했습니다.")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/session")
    def session(request: Request):
        with app.state.db.transaction() as db:
            return dict(authenticate(db, request))

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str, request: Request):
        with app.state.db.transaction() as db:
            actor = authenticate(db, request)
            case = dict(accessible_case(db, actor, case_id))
            for table in ("tasks", "support_requests", "handovers"):
                case[table] = [dict(r) for r in db.execute(
                    f"SELECT * FROM {table} WHERE case_id=? ORDER BY created_at, id", (case_id,))]
            return case

    @app.get("/api/cases/{case_id}/timeline")
    def timeline(case_id: str, request: Request):
        with app.state.db.transaction() as db:
            actor = authenticate(db, request)
            accessible_case(db, actor, case_id)
            return [{**dict(row), "payload": json.loads(row["payload"])} for row in db.execute(
                "SELECT * FROM audit_events WHERE case_id=? ORDER BY new_version", (case_id,))]

    @app.post("/api/cases/{case_id}/tasks", status_code=201)
    def create_task(case_id: str, body: TaskCreate, request: Request):
        def operation(db, actor, case):
            admin(actor)
            member(db, actor, body.assignee_id)
            task_id = uid()
            db.execute("INSERT INTO tasks (id, case_id, type, assignee_id, requester_id, question, callback_needed, status, reply, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'REQUESTED', NULL, ?)",
                       (task_id, case_id, body.type, body.assignee_id, actor["user_id"],
                        body.question, body.callback_needed, now()))
            participate(db, case_id, body.assignee_id)
            return {"task_id": task_id, "status": "REQUESTED", "owner_id": case["owner_id"]}
        return mutate(request, case_id, body, "TASK_CREATED", operation, 201)

    @app.patch("/api/tasks/{task_id}")
    def update_task(task_id: str, body: TaskUpdate, request: Request):
        case_id = resource_case(request, "tasks", task_id)
        def operation(db, actor, case):
            task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if actor["user_id"] != task["assignee_id"]:
                fail(403, "TASK_FORBIDDEN", "업무 수행자만 회신할 수 있습니다.")
            allowed = {"REQUESTED": {"ACKNOWLEDGED", "COMPLETED"}, "ACKNOWLEDGED": {"COMPLETED"}}
            if body.status not in allowed.get(task["status"], set()):
                fail(409, "INVALID_TRANSITION", "허용되지 않는 업무 상태 변경입니다.")
            if body.status == "COMPLETED" and not body.reply:
                fail(422, "REPLY_REQUIRED", "완료 회신을 입력하세요.")
            db.execute("UPDATE tasks SET status=?, reply=? WHERE id=?", (body.status, body.reply, task_id))
            return {"task_id": task_id, "status": body.status, "reply": body.reply}
        return mutate(request, case_id, body, "TASK_UPDATED", operation)

    @app.post("/api/cases/{case_id}/support-requests", status_code=201)
    def create_support(case_id: str, body: SupportCreate, request: Request):
        def operation(db, actor, case):
            member(db, actor, body.coordinator_id, "ADMIN")
            support_id = uid()
            db.execute("INSERT INTO support_requests (id, case_id, requester_id, coordinator_id, type, reason, status, result, created_at) VALUES (?, ?, ?, ?, ?, ?, 'REQUESTED', NULL, ?)",
                       (support_id, case_id, actor["user_id"], body.coordinator_id,
                        body.type, body.reason, now()))
            participate(db, case_id, body.coordinator_id)
            return {"support_request_id": support_id, "status": "REQUESTED"}
        return mutate(request, case_id, body, "SUPPORT_REQUESTED", operation, 201)

    @app.patch("/api/support-requests/{support_id}")
    def update_support(support_id: str, body: SupportUpdate, request: Request):
        case_id = resource_case(request, "support_requests", support_id)
        def operation(db, actor, case):
            admin(actor)
            support = db.execute("SELECT * FROM support_requests WHERE id=?", (support_id,)).fetchone()
            if actor["user_id"] != support["coordinator_id"]:
                fail(403, "SUPPORT_FORBIDDEN", "지정 지원 담당자가 확인해야 합니다.")
            allowed = {"REQUESTED": {"ACKNOWLEDGED"}, "ACKNOWLEDGED": {"IN_PROGRESS", "COMPLETED"},
                       "IN_PROGRESS": {"COMPLETED"}}
            if body.status not in allowed.get(support["status"], set()):
                fail(409, "INVALID_TRANSITION", "지원 수신 확인과 조치 순서를 확인하세요.")
            if body.status == "COMPLETED" and not body.result:
                fail(422, "RESULT_REQUIRED", "지원 결과를 입력하세요.")
            db.execute("UPDATE support_requests SET status=?, result=? WHERE id=?",
                       (body.status, body.result, support_id))
            return {"support_request_id": support_id, "status": body.status, "result": body.result}
        return mutate(request, case_id, body, "SUPPORT_UPDATED", operation)

    @app.post("/api/cases/{case_id}/handovers", status_code=201)
    def create_handover(case_id: str, body: HandoverCreate, request: Request):
        def operation(db, actor, case):
            admin(actor)
            if actor["user_id"] != case["owner_id"]:
                fail(403, "OWNER_REQUIRED", "현재 총괄자가 인계를 요청해야 합니다.")
            member(db, actor, body.to_owner_id, "ADMIN")
            if body.to_owner_id == case["owner_id"]:
                fail(422, "SAME_OWNER", "다른 총괄자를 지정하세요.")
            if db.execute("SELECT 1 FROM handovers WHERE case_id=? AND status='PENDING'", (case_id,)).fetchone():
                fail(409, "HANDOVER_PENDING", "진행 중인 인계가 있습니다.")
            handover_id = uid()
            db.execute("INSERT INTO handovers (id, case_id, from_owner_id, to_owner_id, reason, status, created_at) VALUES (?, ?, ?, ?, ?, 'PENDING', ?)",
                       (handover_id, case_id, case["owner_id"], body.to_owner_id, body.reason, now()))
            return {"handover_id": handover_id, "status": "PENDING", "owner_id": case["owner_id"]}
        return mutate(request, case_id, body, "HANDOVER_REQUESTED", operation, 201)

    @app.post("/api/handovers/{handover_id}/accept")
    def accept_handover(handover_id: str, body: Command, request: Request):
        case_id = resource_case(request, "handovers", handover_id)
        def operation(db, actor, case):
            admin(actor)
            handover = db.execute("SELECT * FROM handovers WHERE id=?", (handover_id,)).fetchone()
            if actor["user_id"] != handover["to_owner_id"]:
                fail(403, "HANDOVER_FORBIDDEN", "지정 인수자만 수락할 수 있습니다.")
            if handover["status"] != "PENDING" or case["owner_id"] != handover["from_owner_id"]:
                fail(409, "INVALID_TRANSITION", "인계 상태가 변경되었습니다.")
            participate(db, case_id, actor["user_id"])
            db.execute("UPDATE cases SET owner_id=? WHERE id=?", (actor["user_id"], case_id))
            db.execute("UPDATE handovers SET status='ACCEPTED' WHERE id=?", (handover_id,))
            return {"handover_id": handover_id, "status": "ACCEPTED", "owner_id": actor["user_id"]}
        return mutate(request, case_id, body, "HANDOVER_ACCEPTED", operation)

    def transition(case_id, body, request, target):
        def operation(db, actor, case):
            admin(actor)
            if actor["user_id"] != case["owner_id"]:
                fail(403, "OWNER_REQUIRED", "현재 총괄자가 처리해야 합니다.")
            if case["status"] == target:
                fail(409, "INVALID_TRANSITION", "이미 해당 상태입니다.")
            if target == "CLOSED":
                pending = {}
                for table, finished in (("tasks", "COMPLETED"), ("support_requests", "COMPLETED"),
                                        ("handovers", "ACCEPTED")):
                    pending[table] = db.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE case_id=? AND status!=?",
                        (case_id, finished)).fetchone()[0]
                if any(pending.values()):
                    fail(409, "OPEN_WORK_REMAINS", "남은 업무·지원·인계를 확인하세요.", pending=pending)
                blockers = app.state.closure.check_closure(db, actor, case_id)
                if blockers:
                    fail(409, "OPEN_WORK_REMAINS", "남은 답변·후속 의무를 확인하세요.", blockers=blockers)
            db.execute("UPDATE cases SET status=? WHERE id=?", (target, case_id))
            return {"status": target, "reason": body.reason}
        return mutate(request, case_id, body, "CASE_" + target, operation, allow_closed=target == "OPEN")

    @app.post("/api/cases/{case_id}/close")
    def close_case(case_id: str, body: CaseTransition, request: Request):
        return transition(case_id, body, request, "CLOSED")

    @app.post("/api/cases/{case_id}/reopen")
    def reopen_case(case_id: str, body: CaseTransition, request: Request):
        return transition(case_id, body, request, "OPEN")

    def openapi_contract():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["Session"] = {
            "type": "http", "scheme": "bearer",
            "description": "개발 시드가 발급한 8시간 세션. 기관 인증은 미구현.",
        }
        for path, operations in schema["paths"].items():
            if not path.startswith("/api/"):
                continue
            for method, operation in operations.items():
                operation["security"] = [{"Session": []}]
                if method in ("post", "patch", "delete"):
                    operation.setdefault("parameters", []).append({
                        "name": "Idempotency-Key", "in": "header", "required": True,
                        "schema": {"type": "string", "minLength": 1, "maxLength": 128},
                        "description": "같은 요청 재시도에는 같은 키와 본문 사용",
                    })
        app.openapi_schema = schema
        return schema

    app.openapi = openapi_contract
    return app
