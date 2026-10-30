"""Guardian identity/relationship boundary for A's public DTOs.

Staff and guardian sessions intentionally use different namespaces. Identity-provider
verification is not simulated by a public login or a caller-supplied guardian ID.
"""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from .access import accessible_case, admin, authenticate, fail
from .commands import mutate
from .db import now, token_hash, uid
from .models import Command, Identifier, Text

router = APIRouter()


class GuardianLink(Command):
    guardian_id: Identifier
    verification_note: Text


class GuardianRevoke(Command):
    reason: Text


def issue_guardian_session(db, guardian_id, school_id):
    """Only for explicit development fixtures or a trusted identity-provider adapter."""
    account = db.execute('SELECT active FROM guardian_accounts WHERE guardian_id=? AND school_id=?',
                         (guardian_id, school_id)).fetchone()
    if not account or not account['active']:
        raise ValueError('Active verified guardian identity required')
    token = secrets.token_urlsafe(32)
    expiry = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
    db.execute('INSERT INTO guardian_sessions(token_hash,guardian_id,school_id,expires_at) VALUES (?,?,?,?)',
               (token_hash(token), guardian_id, school_id, expiry))
    return token


def authenticate_guardian(db, request):
    value = request.headers.get('Authorization', '')
    if not value.startswith('Bearer '):
        fail(401, 'GUARDIAN_SESSION_REQUIRED', '보호자 세션이 필요합니다.')
    actor = db.execute('SELECT a.* FROM guardian_sessions s JOIN guardian_accounts a '
                       'USING(guardian_id,school_id) WHERE s.token_hash=? AND s.expires_at>? AND a.active=1',
                       (token_hash(value[7:]), now())).fetchone()
    if actor is None:
        fail(401, 'GUARDIAN_SESSION_INVALID', '보호자 세션이 유효하지 않습니다.')
    return actor


def guardian_case(db, actor, case_id):
    row = db.execute('SELECT c.* FROM cases c JOIN case_guardian_links g ON g.case_id=c.id '
                     'AND g.school_id=c.school_id WHERE c.id=? AND c.school_id=? '
                     'AND g.guardian_id=? AND g.active=1',
                     (case_id, actor['school_id'], actor['guardian_id'])).fetchone()
    if row is None:
        # No distinction between nonexistent, foreign-school and unrelated cases.
        fail(404, 'GUARDIAN_CASE_NOT_FOUND', '열람 가능한 민원을 찾을 수 없습니다.')
    return row  # Internal only: A must serialize an explicitly allowlisted public DTO.


@router.get('/api/guardian/session')
def guardian_session(request: Request):
    with request.app.state.db.transaction() as db:
        return dict(authenticate_guardian(db, request))


@router.get('/api/guardian/cases/{case_id}/access')
def check_guardian_case(case_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate_guardian(db, request)
        guardian_case(db, actor, case_id)
        return {'case_id': case_id, 'relationship_verified': True}


@router.get('/api/cases/{case_id}/guardian-links')
def list_links(case_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        accessible_case(db, actor, case_id)
        admin(actor)
        return [dict(r) for r in db.execute('SELECT * FROM case_guardian_links WHERE case_id=? ORDER BY verified_at,id', (case_id,))]


@router.post('/api/cases/{case_id}/guardian-links', status_code=201)
def link_guardian(case_id: str, body: GuardianLink, request: Request):
    def operation(db, actor, case):
        admin(actor)
        account = db.execute('SELECT active FROM guardian_accounts WHERE guardian_id=? AND school_id=?',
                             (body.guardian_id, actor['school_id'])).fetchone()
        if account is None or not account['active']:
            fail(422, 'INVALID_GUARDIAN', '같은 학교의 확인된 보호자 계정을 선택하세요.')
        if db.execute('SELECT 1 FROM case_guardian_links WHERE case_id=? AND guardian_id=? AND active=1',
                      (case_id, body.guardian_id)).fetchone():
            fail(409, 'GUARDIAN_ALREADY_LINKED', '이미 연결된 보호자입니다.')
        link_id = uid()
        db.execute('INSERT INTO case_guardian_links(id,case_id,guardian_id,school_id,verified_by,verification_note,verified_at) '
                   'VALUES (?,?,?,?,?,?,?)', (link_id, case_id, body.guardian_id, actor['school_id'],
                                             actor['user_id'], body.verification_note, now()))
        return {'link_id': link_id, 'guardian_id': body.guardian_id, 'active': 1}
    return mutate(request, case_id, body, 'GUARDIAN_LINK_VERIFIED', operation, 201)


@router.post('/api/guardian-links/{link_id}/revoke')
def revoke_guardian_link(link_id: str, body: GuardianRevoke, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        admin(actor)
        link = db.execute('SELECT case_id FROM case_guardian_links WHERE id=? AND school_id=?', (link_id,actor['school_id'])).fetchone()
        if link is None:
            fail(404, 'RESOURCE_NOT_FOUND', '연결을 찾을 수 없습니다.')
        accessible_case(db, actor, link['case_id'])
        case_id = link['case_id']
    def operation(db, actor, case):
        admin(actor)
        link = db.execute('SELECT active FROM case_guardian_links WHERE id=?', (link_id,)).fetchone()
        if not link['active']:
            fail(409, 'INVALID_TRANSITION', '이미 해제된 보호자 연결입니다.')
        db.execute('UPDATE case_guardian_links SET active=0,revoked_by=?,revoked_at=?,revocation_reason=? WHERE id=?',
                   (actor['user_id'], now(), body.reason, link_id))
        return {'link_id': link_id, 'active': 0, 'reason': body.reason}
    # Revocation is a privacy action and remains possible on closed cases.
    return mutate(request, case_id, body, 'GUARDIAN_LINK_REVOKED', operation, allow_closed=True)
