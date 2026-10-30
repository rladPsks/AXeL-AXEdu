import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.agents import Handler, Registry
from backend.decisions import require_current_decision
from backend.main import create_app
from backend.seed import seed
from backend.worker import Worker


@pytest.fixture
def env(tmp_path):
    path = tmp_path / 'decisions.sqlite3'
    creds = seed(path)
    registry = Registry()
    class Result(BaseModel):
        summary: str
    registry.register(Handler('REVIEW_SUPPORT', lambda snapshot: {'summary': '[가상] 제안'}, Result, 'decisions-test', generation_mode='RULE'))
    app = create_app(path, agent_registry=registry, inbox_worker=False)
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','teacher')")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, creds, app, registry


def headers(creds, user='admin', key=None):
    return {'Authorization': 'Bearer ' + creds['tokens'][user], 'Idempotency-Key': key or str(uuid4())}


def body(version=1, **extra):
    return {'expected_version': version, 'decision_type': 'KEEP_REVIEWING', 'reason': '[가상] 미응답 여부 추가 확인',
            'target': '담당 교사와 학교 대응팀', 'route': '학교 관리자 공동 검토', 'remaining_school_work': '이전 답변 전달 여부 확인',
            'observations': [{'source_id': 'demo-case', 'kind': 'UNVERIFIED', 'detail': '사건 제목만으로 이전 응답 여부를 확인할 수 없음'}],
            'input_refs': [{'resource_type': 'CASE', 'resource_id': 'demo-case', 'version': version}], **extra}


def create(client, creds, payload=None, **kwargs):
    return client.post('/api/cases/demo-case/support-decisions', headers=headers(creds, **kwargs), json=payload or body())


def test_decision_snapshot_is_immutable_human_record_and_does_not_transfer_owner(env):
    client, creds, app, _ = env
    response = create(client, creds)
    assert response.status_code == 201 and response.json()['version'] == 2
    decision_id = response.json()['decision_id']
    detail = client.get('/api/support-decisions/' + decision_id, headers=headers(creds)).json()
    assert detail['revision'] == 1 and not detail['stale']
    assert detail['decided_by'] == 'admin' and detail['recorded_case_version'] == 2
    assert detail['snapshot']['observations'][0]['kind'] == 'UNVERIFIED'
    assert detail['snapshot']['sources'][0]['data']['version'] == 1
    snapshot = client.get(f'/api/support-decisions/{decision_id}/snapshot?expected_case_version=2', headers=headers(creds))
    assert snapshot.status_code == 200 and snapshot.json() == detail
    assert client.get('/api/cases/demo-case', headers=headers(creds)).json()['owner_id'] == 'admin'
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM support_requests').fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE support_decisions SET decision_type='EXTERNAL_SUPPORT'")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('DELETE FROM support_decisions')


def test_revision_chain_and_report_reject_superseded_or_changed_case(env):
    client, creds, app, _ = env
    first = create(client, creds).json()['decision_id']
    before = client.get('/api/support-decisions/' + first, headers=headers(creds)).json()['snapshot']
    assert create(client, creds, body(2)).json()['code'] == 'DECISION_CHAIN_CONFLICT'
    second = create(client, creds, body(2, supersedes_id=first, reason='[가상] 새 사실 확인'))
    assert second.status_code == 201
    listing = client.get('/api/cases/demo-case/support-decisions', headers=headers(creds)).json()
    assert [item['revision'] for item in listing] == [2, 1]
    assert listing[1]['snapshot'] == before and listing[1]['superseded'] and listing[1]['stale']
    assert not listing[0]['stale']
    assert client.get(f'/api/support-decisions/{first}/snapshot?expected_case_version=3', headers=headers(creds)).json()['code'] == 'STALE_SUPPORT_DECISION'
    new_id = second.json()['decision_id']
    changed = client.post('/api/cases/demo-case/tasks', headers=headers(creds), json={'expected_version': 3, 'type': 'FOLLOW_UP', 'assignee_id': 'teacher', 'question': '추가 사실 확인'})
    assert changed.status_code == 201
    assert client.get(f'/api/support-decisions/{new_id}/snapshot?expected_case_version=3', headers=headers(creds)).json()['code'] == 'VERSION_CONFLICT'
    assert client.get(f'/api/support-decisions/{new_id}/snapshot?expected_case_version=4', headers=headers(creds)).json()['code'] == 'STALE_SUPPORT_DECISION'


def test_citations_school_role_and_closed_case_are_checked(env):
    client, creds, app, _ = env
    assert create(client, creds, user='teacher').status_code == 403
    assert create(client, creds, body(input_refs=[{'resource_type': 'CASE', 'resource_id': 'foreign-case', 'version': 1}])).status_code == 422
    assert create(client, creds, body(observations=[{'source_id': 'invented', 'kind': 'FACT', 'detail': '없는 근거'}])).json()['code'] == 'INVALID_DECISION_CITATION'
    assert create(client, creds, body(input_refs=[body()['input_refs'][0]] * 2)).json()['code'] == 'DUPLICATE_DECISION_SOURCE'
    decision_id = create(client, creds).json()['decision_id']
    assert client.get('/api/support-decisions/' + decision_id, headers=headers(creds, 'other-admin')).status_code == 404
    assert client.get('/api/support-decisions/' + decision_id, headers=headers(creds, 'teacher')).status_code == 403
    assert client.get('/api/cases/demo-case/support-decisions', headers=headers(creds, 'teacher')).status_code == 403
    assert client.get('/api/support-decisions/' + decision_id, headers={'Authorization': 'Bearer ' + creds['guardian_tokens']['guardian']}).status_code == 401
    assert client.post('/api/cases/demo-case/close', headers=headers(creds), json={'expected_version': 2, 'reason': '가상 종결'}).status_code == 200
    assert create(client, creds, body(3, supersedes_id=decision_id)).json()['code'] == 'CASE_CLOSED'


def test_idempotency_and_audit_failure_roll_back_all_decision_state(env, monkeypatch):
    client, creds, app, _ = env
    def broken(*args, **kwargs):
        raise RuntimeError('audit failed')
    with monkeypatch.context() as patch:
        patch.setattr('backend.commands.audit', broken)
        assert create(client, creds, key='retry').status_code == 500
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM support_decisions').fetchone()[0] == 0
        assert db.execute('SELECT version FROM cases').fetchone()[0] == 1
    first = create(client, creds, key='retry')
    assert first.status_code == 201
    assert create(client, creds, key='retry').json() == first.json()
    assert create(client, creds, body(reason='다른 판단'), key='retry').json()['code'] == 'IDEMPOTENCY_CONFLICT'


def test_pending_school_work_is_snapshotted_and_confidential_content_is_not_in_timeline(env):
    client, creds, app, _ = env
    task = client.post('/api/cases/demo-case/tasks', headers=headers(creds), json={'expected_version': 1, 'type': 'FACT_CHECK', 'assignee_id': 'teacher', 'question': '가상 이전 답변 확인'}).json()['task_id']
    source = client.post('/api/cases/demo-case/files?filename=confidential.txt&expected_version=2&visibility=RESTRICTED', headers={**headers(creds), 'Content-Type': 'application/octet-stream'}, content='[가상] 제한 자료'.encode()).json()['file_id']
    payload = body(3, reason='[가상] 관리자 전용 판단사유', input_refs=[{'resource_type': 'FILE', 'resource_id': source, 'version': 1}], observations=[{'source_id': source, 'kind': 'CLAIM', 'detail': '제한 자료의 당사자 주장'}])
    response = create(client, creds, payload)
    assert response.status_code == 201
    saved = client.get('/api/support-decisions/' + response.json()['decision_id'], headers=headers(creds)).json()['snapshot']
    assert saved['sources'][0]['data']['text'] == '[가상] 제한 자료'
    assert saved['remaining_tasks'][0]['id'] == task
    timeline = client.get('/api/cases/demo-case/timeline', headers=headers(creds, 'teacher')).text
    assert '관리자 전용 판단사유' not in timeline and source not in timeline


def test_only_usable_reviewed_ai_can_be_attached_and_no_automatic_decision_is_created(env):
    client, creds, app, registry = env
    run_id = client.post('/api/cases/demo-case/agent-runs', headers=headers(creds), json={'expected_version': 1, 'purpose': 'REVIEW_SUPPORT', 'input_refs': body()['input_refs']}).json()['run_id']
    assert Worker(app.state.db, registry).process_once()
    assert create(client, creds, body(reviewed_run_id=run_id)).json()['code'] == 'AGENT_RESULT_NOT_READY'
    assert client.get('/api/cases/demo-case/support-decisions', headers=headers(creds)).json() == []
    assert client.post(f'/api/agent-runs/{run_id}/review', headers=headers(creds), json={'expected_version': 1, 'decision': 'ACCEPT', 'reason': '가상 검토 완료'}).status_code == 200
    response = create(client, creds, body(reviewed_run_id=run_id))
    assert response.status_code == 201
    saved = client.get('/api/support-decisions/' + response.json()['decision_id'], headers=headers(creds)).json()['snapshot']
    assert saved['reviewed_ai']['run_id'] == run_id
    assert create(client, creds, body(2, supersedes_id=response.json()['decision_id'], reviewed_run_id=run_id)).json()['code'] == 'STALE_AGENT_RESULT'


def test_report_helper_validates_same_case_and_actual_version(env):
    client, creds, app, _ = env
    decision_id = create(client, creds).json()['decision_id']
    with app.state.db.transaction() as db:
        actor = db.execute("SELECT * FROM memberships WHERE user_id='admin'").fetchone()
        case = dict(db.execute("SELECT * FROM cases WHERE id='demo-case'").fetchone())
        assert require_current_decision(db, actor, case, decision_id)['decision_id'] == decision_id
        from backend.access import DomainError
        with pytest.raises(DomainError, match='같은 민원'):
            require_current_decision(db, actor, {**case, 'id': 'different'}, decision_id)
        with pytest.raises(DomainError, match='최신 민원'):
            require_current_decision(db, actor, {**case, 'version': 1}, decision_id)
