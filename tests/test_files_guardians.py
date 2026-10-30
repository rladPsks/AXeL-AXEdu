import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.seed import seed


@pytest.fixture
def env(tmp_path):
    path = tmp_path / 'private.sqlite3'
    credentials = seed(path)
    app = create_app(path, max_file_bytes=1024)
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','teacher')")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, credentials, app.state.db


def headers(creds, user='admin', *, guardian=False, key=None):
    token = creds['guardian_tokens' if guardian else 'tokens'][user]
    return {'Authorization': 'Bearer ' + token, 'Idempotency-Key': key or str(uuid4()),
            'Content-Type': 'application/octet-stream'}


def json_headers(creds, user='admin', key=None):
    result = headers(creds, user, key=key)
    result['Content-Type'] = 'application/json'
    return result


def upload(client, creds, user='admin', version=1, content=b'private content', **params):
    return client.post('/api/cases/demo-case/files', params={
        'expected_version': version, 'filename': '상담 메모.txt', **params,
    }, content=content, headers=headers(creds, user))


def test_binary_roundtrip_idempotency_and_download_audit(env):
    client, creds, database = env
    params = {'expected_version': 1, 'filename': '상담 메모.txt', 'visibility': 'CASE'}
    h = headers(creds, key='same-upload')
    first = client.post('/api/cases/demo-case/files', params=params, content='[가상] 회신'.encode(), headers=h)
    assert first.status_code == 201
    repeat = client.post('/api/cases/demo-case/files', params=params, content='[가상] 회신'.encode(), headers=h)
    assert repeat.status_code == 201 and repeat.json() == first.json()
    changed = client.post('/api/cases/demo-case/files', params=params, content=b'different', headers=h)
    assert changed.status_code == 409 and changed.json()['code'] == 'IDEMPOTENCY_CONFLICT'
    file_id = first.json()['file_id']
    response = client.get(f'/api/files/{file_id}/download', headers=headers(creds, 'teacher'))
    assert response.content == '[가상] 회신'.encode()
    assert response.headers['content-disposition'].startswith("attachment; filename*=UTF-8''")
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['cache-control'] == 'no-store'
    assert first.json()['sha256'] == hashlib.sha256(response.content).hexdigest()
    metadata = client.get('/api/cases/demo-case/files', headers=headers(creds)).json()
    assert len(metadata) == 1 and 'content' not in metadata[0] and 'path' not in metadata[0]
    with database.transaction() as db:
        assert db.execute('SELECT count(*) FROM private_files').fetchone()[0] == 1
        assert db.execute('SELECT actor_id FROM file_access_events').fetchone()[0] == 'teacher'
        assert db.execute('SELECT version FROM cases').fetchone()[0] == 2
        event = db.execute("SELECT payload FROM audit_events WHERE action='FILE_UPLOADED'").fetchone()[0]
        assert '회신' not in event


def test_private_file_visibility_and_session_boundaries(env):
    client, creds, _ = env
    uploaded = upload(client, creds, 'teacher', visibility='RESTRICTED')
    assert uploaded.status_code == 201
    file_id = uploaded.json()['file_id']
    for user in ['teacher', 'admin', 'deputy']:
        assert client.get(f'/api/files/{file_id}/download', headers=headers(creds, user)).status_code == 200
    for user, expected in [('outsider',403),('other-admin',404)]:
        assert client.get(f'/api/files/{file_id}/download', headers=headers(creds, user)).status_code == expected
    foreign=client.get(f'/api/files/{file_id}/download', headers=headers(creds,'other-admin')).json()
    missing=client.get('/api/files/missing/download', headers=headers(creds,'other-admin')).json()
    assert {k:v for k,v in foreign.items() if k!='request_id'}=={k:v for k,v in missing.items() if k!='request_id'}
    assert client.get(f'/api/files/{file_id}/download').status_code == 401
    assert client.get(f'/api/files/{file_id}/download', headers=headers(creds,'guardian',guardian=True)).status_code == 401


def test_restricted_file_is_hidden_from_other_participating_teacher(env):
    client, creds, database = env
    with database.transaction() as db:
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','outsider')")
    file_id = upload(client, creds, 'teacher', visibility='RESTRICTED').json()['file_id']
    assert client.get('/api/cases/demo-case/files', headers=headers(creds,'outsider')).json() == []
    history=client.get('/api/cases/demo-case/timeline',headers=headers(creds,'outsider'))
    assert '상담 메모.txt' not in history.text and file_id not in history.text
    assert client.get(f'/api/files/{file_id}/download', headers=headers(creds,'outsider')).status_code == 403
    with database.transaction() as db:
        db.execute("DELETE FROM case_participants WHERE user_id='teacher'")
    assert client.get(f'/api/files/{file_id}/download', headers=headers(creds,'teacher')).status_code == 403


@pytest.mark.parametrize('params, content, code', [
    ({'filename':'../escape.txt'}, b'hello', 'INVALID_FILENAME'),
    ({'filename':'bad\r\nname.txt'}, b'hello', 'INVALID_FILENAME'),
    ({'filename':'fake.pdf'}, b'not a pdf', 'UNSUPPORTED_FILE'),
    ({'filename':'file.txt','category':'AUDIO'}, b'not audio', 'UNSUPPORTED_FILE'),
    ({}, b'', 'EMPTY_FILE'),
])
def test_invalid_upload_does_not_modify_domain(env, params, content, code):
    client, creds, database = env
    response = upload(client, creds, content=content, **params)
    assert response.status_code == 422 and response.json()['code'] == code
    with database.transaction() as db:
        assert db.execute('SELECT count(*) FROM private_files').fetchone()[0] == 0
        assert db.execute('SELECT version FROM cases').fetchone()[0] == 1


def test_file_limit_and_audit_rollback(env):
    client, creds, database = env
    assert upload(client, creds, content=b'x'*1025).status_code == 413
    with database.transaction() as db:
        db.execute("CREATE TRIGGER fail_file_audit BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT,'fail'); END")
    assert upload(client, creds).status_code == 500
    with database.transaction() as db:
        assert db.execute('SELECT count(*) FROM private_files').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM idempotency').fetchone()[0] == 0
        assert db.execute('SELECT version FROM cases').fetchone()[0] == 1


def test_guardian_relationship_verified_revoked_and_separate_from_staff(env):
    client, creds, database = env
    guardian_headers = headers(creds,'guardian',guardian=True)
    assert client.get('/api/guardian/session', headers=guardian_headers).json()['guardian_id'] == 'guardian'
    assert client.get('/api/session', headers=guardian_headers).status_code == 401
    assert client.get('/api/guardian/session', headers=headers(creds)).status_code == 401
    assert client.get('/api/guardian/cases/demo-case/access', headers=guardian_headers).status_code == 404
    linked = client.post('/api/cases/demo-case/guardian-links', headers=json_headers(creds),
                         json={'expected_version':1,'guardian_id':'guardian','verification_note':'[가상] 학교 대면 확인'})
    assert linked.status_code == 201
    assert client.get('/api/guardian/cases/demo-case/access', headers=guardian_headers).json() == {
        'case_id':'demo-case','relationship_verified':True}
    assert client.get('/api/cases/demo-case', headers=guardian_headers).status_code == 401
    for other in ['other-guardian','foreign-guardian']:
        assert client.get('/api/guardian/cases/demo-case/access', headers=headers(creds,other,guardian=True)).status_code == 404
    link_id = linked.json()['link_id']
    teacher_history=client.get('/api/cases/demo-case/timeline',headers=headers(creds,'teacher'))
    assert link_id not in teacher_history.text and 'GUARDIAN_LINK_VERIFIED' not in teacher_history.text
    revoked = client.post(f'/api/guardian-links/{link_id}/revoke', headers=json_headers(creds),
                          json={'expected_version':2,'reason':'[가상] 관계 종료'})
    assert revoked.status_code == 200
    assert client.get('/api/guardian/cases/demo-case/access', headers=guardian_headers).status_code == 404
    with database.transaction() as db:
        row = db.execute('SELECT * FROM case_guardian_links').fetchone()
        assert row['verified_by'] == row['revoked_by'] == 'admin' and row['active'] == 0
        assert db.execute('SELECT version FROM cases').fetchone()[0] == 3


def test_guardian_link_permissions_and_deactivated_or_expired_identity(env):
    client, creds, database = env
    body = {'expected_version':1,'guardian_id':'guardian','verification_note':'[가상] 확인'}
    assert client.post('/api/cases/demo-case/guardian-links', headers=json_headers(creds,'teacher'),json=body).status_code == 403
    assert client.post('/api/cases/demo-case/guardian-links', headers=json_headers(creds),json={**body,'guardian_id':'foreign-guardian'}).status_code == 422
    assert client.post('/api/cases/demo-case/guardian-links', headers=json_headers(creds),json={**body,'role':'ADMIN'}).status_code == 422
    with database.transaction() as db:
        db.execute("UPDATE guardian_accounts SET active=0 WHERE guardian_id='guardian'")
        db.execute("UPDATE guardian_sessions SET expires_at='2000-01-01' WHERE guardian_id='other-guardian'")
    for user in ['guardian','other-guardian']:
        assert client.get('/api/guardian/session', headers=headers(creds,user,guardian=True)).status_code == 401
    with database.transaction() as db:
        assert db.execute('SELECT token_hash FROM guardian_sessions LIMIT 1').fetchone()[0] != creds['guardian_tokens']['guardian']


def test_guardian_revocation_remains_available_after_case_closure(env):
    client,creds,database=env
    linked=client.post('/api/cases/demo-case/guardian-links',headers=json_headers(creds),
                       json={'expected_version':1,'guardian_id':'guardian','verification_note':'[가상] 확인'})
    with database.transaction() as db:
        db.execute("UPDATE cases SET status='CLOSED' WHERE id='demo-case'")
    revoked=client.post('/api/guardian-links/'+linked.json()['link_id']+'/revoke',headers=json_headers(creds),
                        json={'expected_version':2,'reason':'종결 후 관계 해제'})
    assert revoked.status_code==200
    assert client.get('/api/guardian/cases/demo-case/access',headers=headers(creds,'guardian',guardian=True)).status_code==404
    with database.transaction() as db:
        assert db.execute('SELECT status FROM cases').fetchone()[0]=='CLOSED'
