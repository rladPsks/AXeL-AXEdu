"""Persisted generation jobs. A/B handlers return proposals, never domain side effects."""
import json
from dataclasses import dataclass, field
from typing import Callable, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from .access import accessible_case, authenticate, fail, DomainError
from .commands import mutate
from .db import now, uid
from .files import file_access
from .models import Command, Identifier, Text

router = APIRouter()


class ProviderFailure(Exception):
    def __init__(self, code, message, retryable=False):
        self.code, self.message, self.retryable = code, message, retryable


@dataclass(frozen=True)
class Handler:
    purpose: str
    execute: Callable[[dict], dict]
    result_model: type[BaseModel]
    version: str
    generation_mode: Literal['MODEL', 'RULE', 'MANUAL'] = 'MODEL'
    requires_review: bool = True
    max_attempts: int = 3
    metadata: dict = field(default_factory=dict)


class Registry:
    def __init__(self):
        self.handlers = {}

    def register(self, handler):
        if handler.purpose in self.handlers or not 1 <= handler.max_attempts <= 5:
            raise ValueError('Duplicate handler or invalid retry bound')
        self.handlers[handler.purpose] = handler


class InputRef(BaseModel):
    model_config = ConfigDict(extra='forbid')
    resource_type: Literal['CASE', 'TASK', 'SUPPORT_REQUEST', 'FILE', 'DOCUMENT_VERSION']
    resource_id: Identifier
    version: int = Field(ge=1)


class RunStart(Command):
    purpose: Identifier
    input_refs: list[InputRef] = Field(min_length=1, max_length=20)
    retry_of_run_id: Identifier | None = None


class RunReview(Command):
    decision: Literal['ACCEPT', 'REJECT']
    reason: Text
    accept_stale: bool = False


class RunCancel(Command):
    reason: Text


def event(db, run_id, status, step, actor_id, detail=None):
    db.execute('INSERT INTO agent_run_events(id,run_id,status,step,actor_id,detail,created_at) VALUES (?,?,?,?,?,?,?)',
               (uid(), run_id, status, step, actor_id, json.dumps(detail,ensure_ascii=False) if detail else None, now()))


def run_access(db, actor, run_id):
    run = db.execute('SELECT * FROM agent_runs WHERE id=? AND school_id=?', (run_id,actor['school_id'])).fetchone()
    if run is None:
        fail(404, 'RUN_NOT_FOUND', '실행을 찾을 수 없습니다.')
    case = accessible_case(db, actor, run['case_id'])
    if actor['role'] != 'ADMIN' and actor['user_id'] != run['requested_by']:
        fail(403, 'RUN_FORBIDDEN', '이 생성 결과를 열람할 권한이 없습니다.')
    for source in json.loads(run['snapshot'])['sources']:
        if source['ref']['resource_type'] == 'FILE':
            file_access(db,actor,source['ref']['resource_id'])
        elif source['ref']['resource_type'] == 'DOCUMENT_VERSION':
            from .evidence import document_version
            document_version(db,actor,source['ref']['resource_id'])
    return run, case


def snapshot(db, actor, case, refs):
    sources = []
    for ref in refs:
        if ref.resource_type == 'CASE':
            if ref.resource_id != case['id']:
                fail(422, 'INPUT_CASE_MISMATCH', '같은 사건의 입력을 선택하세요.')
            item = dict(case)
        elif ref.resource_type == 'FILE':
            item = dict(file_access(db, actor, ref.resource_id))
            if item['category'] == 'AUDIO':
                fail(422, 'AUDIO_CONSENT_REQUIRED', '음성은 동의 확인이 포함된 전사 경로에서 처리해야 합니다.')
            if item['media_type'] == 'text/plain':
                raw = db.execute('SELECT content FROM private_files WHERE id=?', (ref.resource_id,)).fetchone()[0]
                item['text'] = raw.decode('utf-8-sig')[:10000]
                item['text_truncated'] = len(raw.decode('utf-8-sig')) > 10000
        elif ref.resource_type == 'DOCUMENT_VERSION':
            from .evidence import document_version
            item = dict(document_version(db,actor,ref.resource_id))
        else:
            table = {'TASK': 'tasks', 'SUPPORT_REQUEST': 'support_requests'}[ref.resource_type]
            row = db.execute(f'SELECT * FROM {table} WHERE id=?', (ref.resource_id,)).fetchone()
            if row is None:
                fail(422, 'INPUT_NOT_FOUND', '저장된 입력을 찾을 수 없습니다.')
            item = dict(row)
        if item.get('case_id', item.get('id')) != case['id']:
            fail(422, 'INPUT_CASE_MISMATCH', '같은 사건의 입력을 선택하세요.')
        expected = item['revision'] if ref.resource_type == 'DOCUMENT_VERSION' else (1 if ref.resource_type == 'FILE' else case['version'])
        if ref.version != expected:
            fail(409, 'INPUT_VERSION_CONFLICT', '입력 자료의 최신 버전을 확인하세요.')
        sources.append({'ref': ref.model_dump(), 'data': item})
    return {'case_id': case['id'], 'input_case_version': case['version'], 'sources': sources}


def serialize(run, case):
    return {'run_id': run['id'], 'case_id': run['case_id'], 'purpose': run['purpose'],
            'status': run['status'], 'step': run['step'], 'input_case_version': run['input_case_version'],
            'result': json.loads(run['result']) if run['result'] else None,
            'error': json.loads(run['error']) if run['error'] else None,
            'generation_mode': run['generation_mode'], 'attempts': run['attempts'],
            'retry_of_run_id': run['retry_of_run_id'], 'stale': run['input_case_version'] != case['version'],
            'reviewed_case_version': run['reviewed_case_version'], 'created_at': run['created_at']}


@router.get('/api/agent-capabilities')
def capabilities(request: Request):
    with request.app.state.db.transaction() as db:
        authenticate(db, request)
    return [{'purpose': h.purpose, 'generation_mode': h.generation_mode, 'version': h.version}
            for h in request.app.state.agent_registry.handlers.values()]


@router.post('/api/cases/{case_id}/agent-runs', status_code=202)
def start_run(case_id: str, body: RunStart, request: Request):
    def operation(db, actor, case):
        handler = request.app.state.agent_registry.handlers.get(body.purpose)
        if handler is None:
            fail(503, 'AGENT_UNAVAILABLE', '이 생성 기능의 공급자 설정 또는 핸들러가 준비되지 않았습니다.')
        if body.retry_of_run_id:
            old, _ = run_access(db, actor, body.retry_of_run_id)
            if old['case_id'] != case_id or old['purpose'] != body.purpose or old['status'] not in {'FAILED', 'CANCELLED'}:
                fail(409, 'INVALID_RETRY', '실패·취소한 같은 목적의 실행만 다시 요청할 수 있습니다.')
        saved = snapshot(db, actor, case, body.input_refs)
        if len(json.dumps(saved,ensure_ascii=False).encode()) > 1024*1024:
            fail(413,'AGENT_INPUT_TOO_LARGE','선택한 입력이 너무 큽니다. 자료를 나누어 검토하세요.')
        run_id = uid()
        db.execute('INSERT INTO agent_runs(id,case_id,school_id,requested_by,purpose,input_case_version,input_refs,snapshot,'
                   'status,step,generation_mode,handler_version,provider_metadata,max_attempts,retry_of_run_id,created_at,updated_at) '
                   "VALUES (?,?,?,?,?,?,?,?,'QUEUED','queued',?,?,?,?,?,?,?)",
                   (run_id,case_id,actor['school_id'],actor['user_id'],body.purpose,case['version'],
                    body.model_dump_json(include={'input_refs'}),json.dumps(saved,ensure_ascii=False),
                    handler.generation_mode,handler.version,json.dumps(handler.metadata),handler.max_attempts,
                    body.retry_of_run_id,now(),now()))
        event(db, run_id, 'QUEUED', 'queued', actor['user_id'])
        return {'run_id': run_id, 'status': 'QUEUED', 'input_case_version': case['version']}
    return mutate(request,case_id,body,'AGENT_REQUESTED',operation,202,advance_case=False)


@router.get('/api/cases/{case_id}/agent-runs')
def list_runs(case_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        case = accessible_case(db, actor, case_id)
        results=[]
        for run in db.execute("SELECT * FROM agent_runs WHERE case_id=? AND (?='ADMIN' OR requested_by=?) ORDER BY created_at,id",
                              (case_id,actor['role'],actor['user_id'])).fetchall():
            try:
                run_access(db,actor,run['id'])
            except DomainError:
                continue
            results.append(serialize(run,case))
        return results


@router.get('/api/agent-runs/{run_id}')
def get_run(run_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        run, case = run_access(db,actor,run_id)
        return serialize(run,case)


def case_for_run(request, run_id):
    with request.app.state.db.transaction() as db:
        run, _ = run_access(db,authenticate(db,request),run_id)
        return run['case_id']


@router.post('/api/agent-runs/{run_id}/review')
def review_run(run_id: str, body: RunReview, request: Request):
    case_id = case_for_run(request,run_id)
    def operation(db, actor, case):
        run, _ = run_access(db,actor,run_id)
        can_recheck = run['status'] == 'SUCCEEDED' and run['reviewed_case_version'] != case['version']
        if run['status'] != 'WAITING_REVIEW' and not can_recheck:
            fail(409,'INVALID_TRANSITION','검토 대기 결과만 확인할 수 있습니다.')
        if body.decision == 'ACCEPT' and run['input_case_version'] != case['version'] and not body.accept_stale:
            fail(409,'STALE_AGENT_RESULT','생성 후 사건이 변경되었습니다. 변경 내용을 대조한 뒤 다시 검토하세요.')
        status = 'SUCCEEDED' if body.decision == 'ACCEPT' else 'CANCELLED'
        db.execute('UPDATE agent_runs SET status=?,step=?,reviewed_by=?,reviewed_case_version=?,updated_at=? WHERE id=?',
                   (status, 'reviewed', actor['user_id'],case['version'],now(),run_id))
        event(db,run_id,status,'reviewed',actor['user_id'],{'reason':body.reason,'accept_stale':body.accept_stale})
        return {'run_id':run_id,'status':status}
    return mutate(request,case_id,body,'AGENT_REVIEWED',operation,advance_case=False)


@router.post('/api/agent-runs/{run_id}/cancel')
def cancel_run(run_id: str, body: RunCancel, request: Request):
    case_id = case_for_run(request,run_id)
    def operation(db, actor, case):
        run, _ = run_access(db,actor,run_id)
        if run['status'] not in {'QUEUED','RUNNING','WAITING_REVIEW'}:
            fail(409,'INVALID_TRANSITION','진행 중인 실행만 취소할 수 있습니다.')
        db.execute("UPDATE agent_runs SET status='CANCELLED',step='cancelled',lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",(now(),run_id))
        event(db,run_id,'CANCELLED','cancelled',actor['user_id'],{'reason':body.reason})
        return {'run_id':run_id,'status':'CANCELLED'}
    return mutate(request,case_id,body,'AGENT_CANCELLED',operation,allow_closed=True,advance_case=False)


def require_usable_result(db, actor, case, run_id, purpose):
    """Call inside A/B's own domain mutation before applying a reviewed proposal."""
    run, _ = run_access(db,actor,run_id)
    if run['case_id'] != case['id'] or run['purpose'] != purpose or run['status'] != 'SUCCEEDED':
        fail(409,'AGENT_RESULT_NOT_READY','같은 사건의 검토 완료 결과를 선택하세요.')
    version = run['reviewed_case_version'] if run['reviewed_case_version'] is not None else run['input_case_version']
    if version != case['version']:
        fail(409,'STALE_AGENT_RESULT','사건이 변경되어 결과를 다시 검토해야 합니다.')
    return json.loads(run['result'])
