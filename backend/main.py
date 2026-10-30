import json
import logging
import os
from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from .db import Database, now, uid
from .access import DomainError, fail, authenticate, accessible_case, admin, member, participate
from .commands import mutate, resource_case
from .closure import ClosureRegistry
from .queries import router as query_router
from .files import router as files_router, upload_limit, file_access
from .guardians import router as guardians_router
from .agents import router as agents_router, event as agent_event
from .runtime import build_registry
from .worker import Worker
from .seed import seed
from .demo import router as demo_router
from .activities import router as activities_router
from .recordings import router as recordings_router
from .dashboard import router as dashboard_router
from .decisions import router as decisions_router
from .evidence import router as evidence_router
from .comparisons import router as comparisons_router
from .comparison_review import router as comparison_review_router
from .coordination import router as coordination_router, resolve_support
from .scheduling import router as scheduling_router
from .notifications import router as notifications_router, enqueue, dispatch_once
from .features.intake import router as intake_router
from .models import (CaseTransition, Command, HandoverCreate, SupportCreate,
                     SupportUpdate, TaskCreate, TaskUpdate)


def create_app(db_path=None, *, feature_routers=(), closure_guards=(), max_file_bytes=None, agent_registry=None, inbox_worker=True):
    @asynccontextmanager
    async def lifespan(app):
        if os.getenv('SCHOOL_AGENT_AUTO_SEED','0')=='1':
            seed(app.state.db.path,if_empty=True)
        stop=Event()
        def deliver():
            while not stop.is_set():
                try:
                    dispatch_once(app.state.db)
                except Exception as exc:
                    logging.getLogger(__name__).error('inbox_dispatch_failed type=%s',type(exc).__name__)
                stop.wait(2)
        def generate():
            worker=Worker(app.state.db,app.state.agent_registry)
            while not stop.is_set():
                try:
                    if not worker.process_once():
                        stop.wait(1)
                except Exception as exc:
                    logging.getLogger(__name__).error('agent_worker_failed type=%s',type(exc).__name__)
                    stop.wait(1)
        thread=Thread(target=deliver,name='school-inbox',daemon=True) if inbox_worker else None
        agent_thread=Thread(target=generate,name='school-agent',daemon=True) if os.getenv('SCHOOL_AGENT_RUN_WORKER','0')=='1' else None
        if thread:
            thread.start()
        if agent_thread:
            agent_thread.start()
        try:
            yield
        finally:
            stop.set()
            if thread:
                thread.join(timeout=12)
            if agent_thread:
                agent_thread.join(timeout=12)
    app = FastAPI(title="학교 민원 에이전트 — 개발자 B", version="0.1.0",lifespan=lifespan)
    app.state.db = Database(db_path or os.getenv("SCHOOL_AGENT_DB", "data/private/dev.sqlite3"))

    app.state.closure = ClosureRegistry(closure_guards)
    app.state.agent_registry = agent_registry if agent_registry is not None else build_registry()
    app.state.max_file_bytes = upload_limit() if max_file_bytes is None else max_file_bytes
    if app.state.max_file_bytes < 1:
        raise ValueError('max_file_bytes must be positive')
    app.include_router(query_router)
    app.include_router(intake_router)
    app.include_router(files_router)
    app.include_router(guardians_router)
    app.include_router(agents_router)
    app.include_router(coordination_router)
    app.include_router(scheduling_router)
    app.include_router(notifications_router)
    app.include_router(decisions_router)
    app.include_router(evidence_router)
    app.include_router(comparisons_router)
    app.include_router(comparison_review_router)
    app.include_router(activities_router)
    app.include_router(recordings_router)
    app.include_router(dashboard_router)
    if os.getenv('SCHOOL_AGENT_DEMO','0')=='1':
        app.include_router(demo_router)
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

    @app.get("/api/health")
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
            for task in case['tasks']:
                schedule=db.execute('SELECT planned_start_at,due_at,updated_by,updated_at,reason FROM task_schedules WHERE task_id=?',(task['id'],)).fetchone()
                task['schedule']=dict(schedule) if schedule else None
            return case

    @app.get("/api/cases/{case_id}/timeline")
    def timeline(case_id: str, request: Request):
        with app.state.db.transaction() as db:
            actor = authenticate(db, request)
            accessible_case(db, actor, case_id)
            events=[]
            for row in db.execute('SELECT * FROM audit_events WHERE case_id=? ORDER BY new_version',(case_id,)).fetchall():
                payload=json.loads(row['payload'])
                if row['action'].startswith(('CASE_COMPARISON_','CASE_DOCUMENT_')) and actor['role']!='ADMIN':
                    continue
                if row['action'].startswith('GUARDIAN_LINK_') and actor['role']!='ADMIN':
                    continue
                if row['action']=='FILE_UPLOADED':
                    try:
                        file_access(db,actor,payload['file_id'])
                    except DomainError:
                        continue
                events.append({**dict(row),'payload':payload})
            return events

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
            enqueue(db,case_id,body.assignee_id,'TASK_CREATED',task_id,f'task:{task_id}:created')
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
            enqueue(db,case_id,task['requester_id'],'TASK_UPDATED',task_id,f'task:{task_id}:{body.status}')
            auto_run_id = None
            if body.status == "COMPLETED":
                remaining = db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE case_id=? AND status!='COMPLETED'", (case_id,)
                ).fetchone()[0]
                handler = app.state.agent_registry.handlers.get("REVIEW_SUPPORT")
                already = db.execute(
                    "SELECT 1 FROM agent_runs WHERE case_id=? AND purpose='REVIEW_SUPPORT' "
                    "AND status IN ('QUEUED','RUNNING','WAITING_REVIEW')", (case_id,)
                ).fetchone()
                if remaining == 0 and handler is not None and already is None:
                    next_version = case["version"] + 1
                    intake = db.execute("SELECT * FROM case_intakes WHERE case_id=?", (case_id,)).fetchone()
                    case_data = dict(case)
                    case_data["version"] = next_version
                    if intake:
                        intake_data = dict(intake)
                        intake_data["related_people"] = json.loads(intake_data.get("related_people") or "[]")
                        intake_data["classification"] = json.loads(intake_data.pop("classification_json")) if intake_data.get("classification_json") else None
                        intake_data["routing"] = json.loads(intake_data.pop("routing_json")) if intake_data.get("routing_json") else None
                        intake_data["workflow"] = json.loads(intake_data.pop("workflow_json")) if intake_data.get("workflow_json") else None
                        case_data["intake"] = intake_data
                    sources = [{"ref":{"resource_type":"CASE","resource_id":case_id,"version":next_version},"data":case_data}]
                    refs = [{"resource_type":"CASE","resource_id":case_id,"version":next_version}]
                    for row in db.execute("SELECT * FROM tasks WHERE case_id=? ORDER BY created_at,id LIMIT 10",(case_id,)).fetchall():
                        sources.append({"ref":{"resource_type":"TASK","resource_id":row["id"],"version":next_version},"data":dict(row)})
                        refs.append({"resource_type":"TASK","resource_id":row["id"],"version":next_version})
                    snapshot = {"case_id":case_id,"input_case_version":next_version,"sources":sources,
                                "trigger":"ALL_REQUIRED_TASKS_COMPLETED"}
                    auto_run_id = uid()
                    db.execute(
                        "INSERT INTO agent_runs(id,case_id,school_id,requested_by,purpose,input_case_version,input_refs,snapshot,"
                        "status,step,generation_mode,handler_version,provider_metadata,max_attempts,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,'QUEUED','queued',?,?,?,?,?,?)",
                        (auto_run_id,case_id,actor["school_id"],case["owner_id"],"REVIEW_SUPPORT",next_version,
                         json.dumps({"input_refs":refs},ensure_ascii=False),json.dumps(snapshot,ensure_ascii=False),
                         handler.generation_mode,handler.version,json.dumps(handler.metadata),handler.max_attempts,now(),now())
                    )
                    agent_event(db,auto_run_id,"QUEUED","queued",actor["user_id"],
                                {"trigger":"ALL_REQUIRED_TASKS_COMPLETED","task_id":task_id})
            return {"task_id": task_id, "status": body.status, "reply": body.reply,
                    "agent_run_id": auto_run_id}
        return mutate(request, case_id, body, "TASK_UPDATED", operation)

    @app.post("/api/cases/{case_id}/support-requests", status_code=201)
    def create_support(case_id: str, body: SupportCreate, request: Request):
        def operation(db, actor, case):
            member(db, actor, body.coordinator_id, "ADMIN")
            coordinator,routing=resolve_support(db,actor['school_id'],body.coordinator_id)
            support_id = uid()
            db.execute("INSERT INTO support_requests (id, case_id, requester_id, coordinator_id, type, reason, status, result, created_at) VALUES (?, ?, ?, ?, ?, ?, 'REQUESTED', NULL, ?)",
                       (support_id, case_id, actor["user_id"], coordinator,
                        body.type, body.reason, now()))
            db.execute('UPDATE support_requests SET requested_coordinator_id=?,routing_reason=?,assigned_at=? WHERE id=?',
                       (body.coordinator_id,routing,now(),support_id))
            participate(db, case_id, coordinator)
            enqueue(db,case_id,coordinator,'SUPPORT_REQUESTED',support_id,f'support:{support_id}:requested',severity='URGENT' if body.type=='URGENT' else 'NORMAL')
            return {"support_request_id": support_id, "status": "REQUESTED",'coordinator_id':coordinator,'routing_reason':routing}
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
            enqueue(db,case_id,support['requester_id'],'SUPPORT_UPDATED',support_id,f'support:{support_id}:{body.status}',severity='URGENT' if support['type']=='URGENT' else 'NORMAL')
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
            enqueue(db,case_id,body.to_owner_id,'HANDOVER_REQUESTED',handover_id,f'handover:{handover_id}:requested')
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
            db.execute("UPDATE handovers SET status='ACCEPTED',resolved_by=?,resolved_at=? WHERE id=?", (actor['user_id'],now(),handover_id))
            enqueue(db,case_id,handover['from_owner_id'],'HANDOVER_ACCEPTED',handover_id,f'handover:{handover_id}:accepted')
            return {"handover_id": handover_id, "status": "ACCEPTED", "owner_id": actor["user_id"]}
        return mutate(request, case_id, body, "HANDOVER_ACCEPTED", operation)

    def resolve_handover(handover_id,body,request,target):
        case_id=resource_case(request,'handovers',handover_id)
        def operation(db,actor,case):
            admin(actor)
            handover=db.execute('SELECT * FROM handovers WHERE id=?',(handover_id,)).fetchone()
            required=handover['to_owner_id'] if target=='DECLINED' else handover['from_owner_id']
            if actor['user_id']!=required or case['owner_id']!=handover['from_owner_id']:
                fail(403,'HANDOVER_FORBIDDEN','지정된 당사자만 인계 요청을 처리할 수 있습니다.')
            if handover['status']!='PENDING':
                fail(409,'INVALID_TRANSITION','대기 중인 인계만 처리할 수 있습니다.')
            db.execute('UPDATE handovers SET status=?,resolved_by=?,resolved_at=?,resolution_reason=? WHERE id=?',
                       (target,actor['user_id'],now(),body.reason,handover_id))
            recipient=handover['from_owner_id'] if target=='DECLINED' else handover['to_owner_id']
            enqueue(db,case_id,recipient,'HANDOVER_'+target,handover_id,f'handover:{handover_id}:{target}')
            return {'handover_id':handover_id,'status':target,'owner_id':case['owner_id'],'reason':body.reason}
        return mutate(request,case_id,body,'HANDOVER_'+target,operation)

    @app.post('/api/handovers/{handover_id}/decline')
    def decline_handover(handover_id:str,body:CaseTransition,request:Request):
        return resolve_handover(handover_id,body,request,'DECLINED')

    @app.post('/api/handovers/{handover_id}/cancel')
    def cancel_handover(handover_id:str,body:CaseTransition,request:Request):
        return resolve_handover(handover_id,body,request,'CANCELLED')

    def transition(case_id, body, request, target):
        def operation(db, actor, case):
            admin(actor)
            if actor["user_id"] != case["owner_id"]:
                fail(403, "OWNER_REQUIRED", "현재 총괄자가 처리해야 합니다.")
            if case["status"] == target:
                fail(409, "INVALID_TRANSITION", "이미 해당 상태입니다.")
            if target == "CLOSED":
                pending = {}
                for table, finished in (("tasks", "COMPLETED"), ("support_requests", "COMPLETED")):
                    pending[table] = db.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE case_id=? AND status!=?",
                        (case_id, finished)).fetchone()[0]
                pending['handovers']=db.execute("SELECT COUNT(*) FROM handovers WHERE case_id=? AND status='PENDING'",(case_id,)).fetchone()[0]
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
                if method in ("post", "patch", "put", "delete"):
                    operation.setdefault("parameters", []).append({
                        "name": "Idempotency-Key", "in": "header", "required": True,
                        "schema": {"type": "string", "minLength": 1, "maxLength": 128},
                        "description": "같은 요청 재시도에는 같은 키와 본문 사용",
                    })
        app.openapi_schema = schema
        return schema

    app.openapi = openapi_contract
    return app
