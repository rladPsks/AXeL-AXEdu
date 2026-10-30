"""Explicit opt-in public fictional login. Never an institutional identity provider."""
import json

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from .access import fail
from .db import issue_session
from .guardians import issue_guardian_session
from .models import Identifier

router = APIRouter()
ACCOUNTS = (
    {'id': 'admin', 'name': '김○○ 교장', 'role': 'ADMIN', 'kind': 'STAFF', 'school_id': 'demo-school'},
    {'id': 'deputy', 'name': '이○○ 교감', 'role': 'ADMIN', 'kind': 'STAFF', 'school_id': 'demo-school'},
    {'id': 'academic-head', 'name': '박○○ 교무부장', 'role': 'ADMIN', 'kind': 'STAFF', 'school_id': 'demo-school'},
    {'id': 'office-head', 'name': '한○○ 행정실장', 'role': 'ADMIN', 'kind': 'STAFF', 'school_id': 'demo-school'},
    {'id': 'life-head', 'name': '윤○○ 생활부장', 'role': 'ADMIN', 'kind': 'STAFF', 'school_id': 'demo-school'},
    {'id': 'work-support', 'name': '오○○ 업무지원', 'role': 'ADMIN', 'kind': 'STAFF', 'school_id': 'demo-school'},
    {'id': 'teacher', 'name': '최○○ 교사', 'role': 'TEACHER', 'kind': 'STAFF', 'school_id': 'demo-school'},
    {'id': 'outsider', 'name': '정○○ 교사', 'role': 'TEACHER', 'kind': 'STAFF', 'school_id': 'demo-school'},
    {'id': 'other-admin', 'name': '다른 학교 관리자', 'role': 'ADMIN', 'kind': 'STAFF', 'school_id': 'other-school'},
    {'id': 'guardian', 'name': '보호자', 'role': 'GUARDIAN', 'kind': 'GUARDIAN', 'school_id': 'demo-school'},
    {'id': 'other-guardian', 'name': '다른 보호자', 'role': 'GUARDIAN', 'kind': 'GUARDIAN', 'school_id': 'demo-school'},
    {'id': 'foreign-guardian', 'name': '다른 학교 보호자', 'role': 'GUARDIAN', 'kind': 'GUARDIAN', 'school_id': 'other-school'},
)


class DemoLogin(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account: Identifier


def seeded(db):
    # An opt-in flag alone must not turn arbitrary existing accounts into demo identities.
    row = db.execute("SELECT payload FROM audit_events WHERE case_id='demo-case' AND action='DEMO_CASE_CREATED'").fetchone()
    case = db.execute("SELECT school_id FROM cases WHERE id='demo-case'").fetchone()
    if not row or not case or case['school_id'] != 'demo-school' or json.loads(row['payload']).get('fictional') is not True:
        fail(503, 'DEMO_NOT_READY', '시연 데이터가 준비되지 않았습니다.')


def available(db, account):
    if account['kind'] == 'STAFF':
        row = db.execute('SELECT role,active FROM memberships WHERE user_id=? AND school_id=?',
                         (account['id'], account['school_id'])).fetchone()
        return row is not None and row['active'] == 1 and row['role'] == account['role']
    row = db.execute('SELECT active FROM guardian_accounts WHERE guardian_id=? AND school_id=?',
                     (account['id'], account['school_id'])).fetchone()
    return row is not None and row['active'] == 1


def public(account):
    return {key: account[key] for key in ('id', 'name', 'role', 'kind')}


@router.get('/api/demo/accounts')
def accounts(request: Request):
    with request.app.state.db.transaction() as db:
        seeded(db)
        return [public(account) for account in ACCOUNTS if available(db, account)]


@router.post('/api/demo/login')
def login(body: DemoLogin, request: Request):
    account = next((item for item in ACCOUNTS if item['id'] == body.account), None)
    if account is None:
        fail(403, 'DEMO_ACCOUNT_FORBIDDEN', '등록된 시연 계정을 선택하세요.')
    with request.app.state.db.transaction() as db:
        seeded(db)
        if not available(db, account):
            fail(403, 'DEMO_ACCOUNT_FORBIDDEN', '현재 사용할 수 없는 시연 계정입니다.')
        issue = issue_session if account['kind'] == 'STAFF' else issue_guardian_session
        token = issue(db, account['id'], account['school_id'])
        return {'token': token, 'account': public(account)}
