"""Atomic domain commands shared by A and B feature routers."""
import hashlib
import json
from fastapi.responses import JSONResponse
from .db import audit
from .access import authenticate, accessible_case, fail

def command_identity(request,body):
    key=request.headers.get('Idempotency-Key','').strip()
    if not key or len(key)>128:
        fail(422,'IDEMPOTENCY_KEY_REQUIRED','128자 이내의 Idempotency-Key가 필요합니다.')
    return request.method+' '+request.url.path,key,hashlib.sha256(body.model_dump_json().encode()).hexdigest()


def replay_command(db,actor,identity):
    route,key,body_hash=identity
    row=db.execute('SELECT * FROM idempotency WHERE actor_id=? AND school_id=? AND route=? AND key=?',
                   (actor['user_id'],actor['school_id'],route,key)).fetchone()
    if row:
        if row['body_hash']!=body_hash:
            fail(409,'IDEMPOTENCY_CONFLICT','같은 키에 다른 요청을 사용할 수 없습니다.')
        return JSONResponse(json.loads(row['response']),status_code=row['status_code'])
    return None


def save_command(db,actor,identity,response,status=200):
    route,key,body_hash=identity
    db.execute('INSERT INTO idempotency(actor_id,school_id,route,key,body_hash,status_code,response) VALUES (?,?,?,?,?,?,?)',
               (actor['user_id'],actor['school_id'],route,key,body_hash,status,json.dumps(response,ensure_ascii=False)))


def mutate(request, case_id, body, action, operation, status=200, allow_closed=False, advance_case=True):
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 128:
        fail(422, "IDEMPOTENCY_KEY_REQUIRED", "128자 이내의 Idempotency-Key가 필요합니다.")
    route = request.method + " " + request.url.path
    body_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        case = accessible_case(db, actor, case_id)
        scope = (actor["user_id"], actor["school_id"], route, key)
        old = db.execute(
            "SELECT * FROM idempotency WHERE actor_id=? AND school_id=? AND route=? AND key=?",
            scope,
        ).fetchone()
        if old:
            if old["body_hash"] != body_hash:
                fail(409, "IDEMPOTENCY_CONFLICT", "같은 키에 다른 요청을 사용할 수 없습니다.")
            return JSONResponse(json.loads(old["response"]), status_code=old["status_code"])
        if body.expected_version != case["version"]:
            fail(409, "VERSION_CONFLICT", "최신 사건을 조회한 뒤 다시 시도하세요.",
                 case_id=case_id, current_version=case["version"])
        if case["status"] == "CLOSED" and not allow_closed:
            fail(409, "CASE_CLOSED", "사건을 재개한 뒤 변경하세요.")
        result = operation(db, actor, case)
        if {'case_id', 'version'} & result.keys():
            raise ValueError('Command results may not override the shared case identity/version')
        version = case["version"] + int(advance_case)
        if advance_case:
            db.execute("UPDATE cases SET version=? WHERE id=?", (version, case_id))
            audit(db, actor, case_id, action, version, result)
        response = {"case_id": case_id, "version": version, **result}
        db.execute("INSERT INTO idempotency (actor_id, school_id, route, key, body_hash, status_code, response) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (*scope, body_hash, status, json.dumps(response, ensure_ascii=False)))
        return JSONResponse(response, status_code=status)

def resource_case(request, table, resource_id):
    if table not in {"tasks", "support_requests", "handovers"}:
        raise ValueError("Unsupported resource table")
    # Table names only come from endpoint code, never from user input.
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        row = db.execute(f"SELECT case_id FROM {table} WHERE id=? AND case_id IN "
                         "(SELECT id FROM cases WHERE school_id=?)", (resource_id,actor['school_id'])).fetchone()
        if row is None:
            fail(404, "RESOURCE_NOT_FOUND", "대상을 찾을 수 없습니다.")
        accessible_case(db, actor, row["case_id"])
        return row["case_id"]
