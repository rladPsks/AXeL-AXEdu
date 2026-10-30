"""Append-only activity ledger: recorded direct contact, callbacks, counselling and support work."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import field_validator

from .access import accessible_case, authenticate, fail
from .commands import mutate
from .db import now, uid
from .models import Command, Identifier, Text

router = APIRouter()
KINDS = ('DIRECT_CONTACT', 'CALLBACK', 'COUNSEL', 'TASK_WORK', 'SUPPORT_ACTION')


def to_utc(value):
    """Store a timezone-aware instant in one comparable UTC format."""
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        fail(422, 'INVALID_TIME', '시각은 시간대가 포함된 ISO 형식이어야 합니다.')
    if parsed.tzinfo is None:
        fail(422, 'INVALID_TIME', '시각에는 시간대가 필요합니다. 한국 시간이면 +09:00을 붙이세요.')
    return parsed.astimezone(timezone.utc).isoformat()


class ActivityCreate(Command):
    staff_id: Identifier
    kind: Literal['DIRECT_CONTACT', 'CALLBACK', 'COUNSEL', 'TASK_WORK', 'SUPPORT_ACTION']
    occurred_at: str
    # None means "not recorded". It is never silently counted as zero minutes.
    duration_seconds: int | None = None
    note: Text | None = None

    @field_validator('duration_seconds')
    @classmethod
    def bounded(cls, value):
        if value is not None and not 0 <= value <= 86400:
            raise ValueError('duration out of range')
        return value


@router.post('/api/cases/{case_id}/activities', status_code=201)
def record_activity(case_id: str, body: ActivityCreate, request: Request):
    def operation(db, actor, case):
        if actor['role'] != 'ADMIN' and body.staff_id != actor['user_id']:
            fail(403, 'ACTIVITY_FORBIDDEN', '교사는 본인의 활동만 기록할 수 있습니다.')
        staff = db.execute('SELECT role FROM memberships WHERE user_id=? AND school_id=? AND active=1',
                           (body.staff_id, actor['school_id'])).fetchone()
        if staff is None:
            fail(422, 'INVALID_MEMBER', '활성 학교 구성원을 선택하세요.')
        if staff['role'] != 'ADMIN' and not db.execute(
                'SELECT 1 FROM case_participants WHERE case_id=? AND user_id=?',
                (case_id, body.staff_id)).fetchone():
            fail(422, 'STAFF_NOT_IN_CASE', '이 민원에 참여한 구성원의 활동만 기록할 수 있습니다.')
        activity_id = uid()
        db.execute('INSERT INTO activity_logs(id,case_id,school_id,staff_id,recorded_by,kind,occurred_at,'
                   'duration_seconds,note,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (activity_id, case_id, actor['school_id'], body.staff_id, actor['user_id'], body.kind,
                    to_utc(body.occurred_at), body.duration_seconds, body.note, now()))
        return {'activity_id': activity_id, 'duration_recorded': body.duration_seconds is not None}
    # Recording what already happened must not invalidate AI results or be blocked by closure.
    return mutate(request, case_id, body, 'ACTIVITY_RECORDED', operation, 201,
                  allow_closed=True, advance_case=False)


@router.get('/api/cases/{case_id}/activities')
def list_activities(case_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        accessible_case(db, actor, case_id)
        # Time records about colleagues are visible to administrators only.
        rows = db.execute(
            'SELECT id,case_id,staff_id,recorded_by,kind,occurred_at,duration_seconds,note,created_at '
            "FROM activity_logs WHERE case_id=? AND school_id=? AND (?='ADMIN' OR staff_id=?) "
            'ORDER BY occurred_at,id', (case_id, actor['school_id'], actor['role'], actor['user_id'])).fetchall()
        return [dict(row) for row in rows]
