"""Human support decisions and immutable, versioned input for A's report module."""
import json
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .access import accessible_case, admin, authenticate, fail
from .agents import InputRef, require_usable_result, run_access, snapshot
from .commands import mutate
from .db import now, uid
from .files import file_access
from .models import Command, Identifier, Text

router = APIRouter()


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: Identifier
    kind: Literal['FACT', 'CLAIM', 'UNVERIFIED']
    detail: Text


class DecisionCreate(Command):
    decision_type: Literal['INTERNAL_SUPPORT', 'SPECIALIST_SUPPORT', 'EXTERNAL_SUPPORT', 'KEEP_REVIEWING']
    reason: Text
    target: Text
    route: Text
    remaining_school_work: Text
    observations: list[Observation] = Field(min_length=1, max_length=40)
    input_refs: list[InputRef] = Field(min_length=1, max_length=20)
    supersedes_id: Identifier | None = None
    reviewed_run_id: Identifier | None = None


def latest(db, case_id):
    return db.execute('SELECT * FROM support_decisions WHERE case_id=? ORDER BY revision DESC LIMIT 1', (case_id,)).fetchone()


def read_decision(db, actor, decision_id):
    admin(actor)
    row = db.execute('SELECT d.* FROM support_decisions d JOIN cases c ON c.id=d.case_id '
                     'WHERE d.id=? AND c.school_id=?', (decision_id, actor['school_id'])).fetchone()
    if row is None:
        fail(404, 'DECISION_NOT_FOUND', '지원 판단 기록을 찾을 수 없습니다.')
    case = accessible_case(db, actor, row['case_id'])
    saved = json.loads(row['snapshot'])
    for source in saved['sources']:
        if source['ref']['resource_type'] == 'FILE':
            file_access(db, actor, source['ref']['resource_id'])
        elif source['ref']['resource_type'] == 'DOCUMENT_VERSION':
            from .evidence import document_version
            document_version(db, actor, source['ref']['resource_id'])
        elif source['ref']['resource_type']=='COMPARISON_REVIEW':
            from .comparison_review import review_access
            review_access(db,actor,source['ref']['resource_id'])
        elif source['ref']['resource_type']=='COMPARISON_INPUT':
            from .comparison_review import input_access
            input_access(db,actor,source['ref']['resource_id'])
    if saved['reviewed_ai']:
        run_access(db, actor, saved['reviewed_ai']['run_id'])
    return row, case, saved


def serialize(db, row, case, saved, actor):
    current = latest(db, case['id'])
    superseded = current['id'] != row['id']
    from .comparison_review import review_dependency_stale,input_stale
    dependency_stale=any((source['ref']['resource_type']=='COMPARISON_REVIEW' and review_dependency_stale(db,actor,source['data'])) or
                         (source['ref']['resource_type']=='COMPARISON_INPUT' and input_stale(db,actor,source['data'],ignore_anchor=True)) for source in saved['sources'])
    if saved['reviewed_ai']:
        from .agents import comparison_dependencies_stale
        run,_=run_access(db,actor,saved['reviewed_ai']['run_id'])
        dependency_stale=dependency_stale or comparison_dependencies_stale(db,actor,run)
    return {'decision_id': row['id'], 'case_id': row['case_id'], 'revision': row['revision'],
            'supersedes_id': row['supersedes_id'], 'decided_by': row['decided_by'],
            'input_case_version': row['input_case_version'], 'recorded_case_version': row['recorded_case_version'],
            'current_case_version': case['version'], 'superseded': superseded,
            'stale': superseded or row['recorded_case_version'] != case['version'] or dependency_stale,
            'created_at': row['created_at'], 'snapshot': saved}


def require_current_decision(db, actor, case, decision_id):
    """A calls inside its own transaction before using a decision in a report."""
    row, actual, saved = read_decision(db, actor, decision_id)
    if actual['id'] != case['id']:
        fail(409, 'DECISION_CASE_MISMATCH', '같은 사건의 지원 판단을 선택하세요.')
    if actual['version'] != case['version']:
        fail(409, 'VERSION_CONFLICT', '최신 사건을 조회한 뒤 다시 확인하세요.')
    result = serialize(db, row, actual, saved, actor)
    if result['stale']:
        fail(409, 'STALE_SUPPORT_DECISION', '사건이나 지원 판단이 변경되었습니다. 현재 기록을 검토해 새 판단을 남기세요.')
    return result


@router.post('/api/cases/{case_id}/support-decisions', status_code=201)
def create_decision(case_id: str, body: DecisionCreate, request: Request):
    def operation(db, actor, case):
        admin(actor)
        previous = latest(db, case_id)
        if body.supersedes_id != (previous['id'] if previous else None):
            fail(409, 'DECISION_CHAIN_CONFLICT', '최신 판단 기록을 조회한 뒤 변경 사유와 함께 다시 기록하세요.')
        refs = [(ref.resource_type, ref.resource_id) for ref in body.input_refs]
        if len(refs) != len(set(refs)):
            fail(422, 'DUPLICATE_DECISION_SOURCE', '같은 출처를 중복 선택할 수 없습니다.')
        sources = snapshot(db, actor, case, body.input_refs)['sources']
        source_ids = {source['ref']['resource_id'] for source in sources}
        if any(observation.source_id not in source_ids for observation in body.observations):
            fail(422, 'INVALID_DECISION_CITATION', '관찰의 출처는 선택한 저장 자료에 포함되어야 합니다.')
        reviewed_ai = None
        if body.reviewed_run_id:
            result = require_usable_result(db, actor, case, body.reviewed_run_id, 'REVIEW_SUPPORT')
            reviewed_ai = {'run_id': body.reviewed_run_id, 'result': result}
        saved = {'schema_version': 1, 'decision_type': body.decision_type, 'reason': body.reason,
                 'target': body.target, 'route': body.route, 'remaining_school_work': body.remaining_school_work,
                 'observations': [item.model_dump() for item in body.observations], 'sources': sources,
                 'reviewed_ai': reviewed_ai,
                 'remaining_tasks': [dict(row) for row in db.execute("SELECT * FROM tasks WHERE case_id=? AND status!='COMPLETED' ORDER BY created_at,id", (case_id,))],
                 'remaining_support': [dict(row) for row in db.execute("SELECT * FROM support_requests WHERE case_id=? AND status!='COMPLETED' ORDER BY created_at,id", (case_id,))]}
        encoded = json.dumps(saved, ensure_ascii=False)
        if len(encoded.encode()) > 1024 * 1024:
            fail(413, 'DECISION_SNAPSHOT_TOO_LARGE', '판단 자료가 너무 큽니다. 선택 자료와 미완료 업무를 확인하세요.')
        decision_id = uid()
        db.execute('INSERT INTO support_decisions(id,case_id,revision,supersedes_id,decided_by,decision_type,input_case_version,recorded_case_version,snapshot,created_at) '
                   'VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (decision_id, case_id, previous['revision'] + 1 if previous else 1, body.supersedes_id,
                    actor['user_id'], body.decision_type, case['version'], case['version'] + 1, encoded, now()))
        # The teacher-visible audit contains identity only, never confidential observations or file text.
        return {'decision_id': decision_id, 'decision_type': body.decision_type}
    return mutate(request, case_id, body, 'SUPPORT_DECISION_RECORDED', operation, 201)


@router.get('/api/cases/{case_id}/support-decisions')
def list_decisions(case_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        admin(actor)
        case = accessible_case(db, actor, case_id)
        results = []
        for row in db.execute('SELECT * FROM support_decisions WHERE case_id=? ORDER BY revision DESC', (case_id,)):
            _, _, saved = read_decision(db, actor, row['id'])
            results.append(serialize(db, row, case, saved, actor))
        return results


@router.get('/api/support-decisions/{decision_id}')
def get_decision(decision_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        row, case, saved = read_decision(db, actor, decision_id)
        return serialize(db, row, case, saved, actor)


@router.get('/api/support-decisions/{decision_id}/snapshot')
def report_snapshot(decision_id: str, request: Request, expected_case_version: int = Query(ge=1)):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        _, case, _ = read_decision(db, actor, decision_id)
        if expected_case_version != case['version']:
            fail(409, 'VERSION_CONFLICT', '최신 사건을 조회한 뒤 다시 확인하세요.')
        return require_current_decision(db, actor, case, decision_id)
