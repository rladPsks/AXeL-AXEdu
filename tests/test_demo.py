from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.agents import Registry
from backend.db import Database, token_hash
from backend.demo import ACCOUNTS
from backend.main import create_app
from backend.seed import seed


def app_for(path):
    return create_app(path, agent_registry=Registry(), inbox_worker=False)


def test_demo_and_auto_seed_are_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv('SCHOOL_AGENT_DEMO', raising=False)
    monkeypatch.delenv('SCHOOL_AGENT_AUTO_SEED', raising=False)
    app = app_for(tmp_path / 'default.sqlite3')
    with TestClient(app) as client:
        assert client.get('/api/demo/accounts').status_code == 404
        assert client.post('/api/demo/login', json={'account': 'admin'}).status_code == 404
        assert '/api/demo/login' not in client.get('/openapi.json').json()['paths']
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM memberships').fetchone()[0] == 0


def test_auto_seed_runs_once_before_requests_and_never_prints_tokens(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('SCHOOL_AGENT_AUTO_SEED', '1')
    path = tmp_path / 'auto.sqlite3'
    app = app_for(path)
    with TestClient(app) as client:
        assert client.get('/api/health').json() == {'status': 'ok'}
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM memberships').fetchone()[0] == 5
        before = [tuple(row) for row in db.execute('SELECT * FROM sessions ORDER BY token_hash')]
        db.execute("UPDATE cases SET title='[가상] 재시작 보존' WHERE id='demo-case'")
    with TestClient(app_for(path)):
        pass
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM memberships').fetchone()[0] == 5
        assert db.execute('SELECT count(*) FROM audit_events').fetchone()[0] == 1
        assert db.execute('SELECT title FROM cases').fetchone()[0] == '[가상] 재시작 보존'
        assert [tuple(row) for row in db.execute('SELECT * FROM sessions ORDER BY token_hash')] == before
    assert capsys.readouterr().out == ''


def test_if_empty_seed_is_atomic_and_default_cli_behavior_is_preserved(tmp_path):
    path = tmp_path / 'race.sqlite3'
    Database(path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: seed(path, if_empty=True), range(2)))
    assert sum(result is not None for result in results) == 1
    with pytest.raises(SystemExit):
        seed(path)


def test_demo_allowlist_issues_fresh_tokens_with_existing_namespace_access(tmp_path, monkeypatch):
    monkeypatch.setenv('SCHOOL_AGENT_DEMO', '1')
    monkeypatch.setenv('SCHOOL_AGENT_AUTO_SEED', '1')
    app = app_for(tmp_path / 'login.sqlite3')
    with TestClient(app) as client:
        listing = client.get('/api/demo/accounts')
        assert listing.status_code == 200 and len(listing.json()) == len(ACCOUNTS)
        assert all(set(item) == {'id', 'name', 'role', 'kind'} for item in listing.json())
        for account in ACCOUNTS:
            first = client.post('/api/demo/login', json={'account': account['id']})
            second = client.post('/api/demo/login', json={'account': account['id']})
            assert first.status_code == second.status_code == 200
            assert first.json()['token'] != second.json()['token']
            auth = {'Authorization': 'Bearer ' + first.json()['token']}
            own = '/api/session' if account['kind'] == 'STAFF' else '/api/guardian/session'
            other = '/api/guardian/session' if account['kind'] == 'STAFF' else '/api/session'
            assert client.get(own, headers=auth).status_code == 200
            assert client.get(other, headers=auth).status_code == 401
            if account['id'] == 'admin':
                assert client.get('/api/cases/demo-case', headers=auth).status_code == 200
            elif account['kind'] == 'GUARDIAN':
                assert client.get('/api/cases/demo-case', headers=auth).status_code == 401
            with app.state.db.transaction() as db:
                table = 'sessions' if account['kind'] == 'STAFF' else 'guardian_sessions'
                assert db.execute(f'SELECT 1 FROM {table} WHERE token_hash=?', (token_hash(first.json()['token']),)).fetchone()
        assert client.post('/api/demo/login', json={'account': 'not-demo'}).status_code == 403
        assert client.post('/api/demo/login', json={'account': 'admin', 'school_id': 'other-school'}).status_code == 422


def test_demo_refuses_missing_seed_marker_and_inactive_or_changed_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv('SCHOOL_AGENT_DEMO', '1')
    path = tmp_path / 'unseeded.sqlite3'
    app = app_for(path)
    with TestClient(app) as client:
        assert client.get('/api/demo/accounts').status_code == 503
        assert client.post('/api/demo/login', json={'account': 'admin'}).status_code == 503
    seed(path)
    with app.state.db.transaction() as db:
        db.execute("UPDATE memberships SET active=0 WHERE user_id='teacher'")
        db.execute("UPDATE memberships SET role='ADMIN' WHERE user_id='outsider'")
        db.execute("UPDATE guardian_accounts SET active=0 WHERE guardian_id='guardian'")
    with TestClient(app) as client:
        ids = {account['id'] for account in client.get('/api/demo/accounts').json()}
        for account in ('teacher', 'outsider', 'guardian'):
            assert account not in ids
            assert client.post('/api/demo/login', json={'account': account}).status_code == 403


def test_auto_seed_preserves_existing_non_demo_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv('SCHOOL_AGENT_AUTO_SEED', '1')
    monkeypatch.setenv('SCHOOL_AGENT_DEMO', '1')
    app = app_for(tmp_path / 'existing.sqlite3')
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO memberships(user_id,school_id,role) VALUES ('existing','school','ADMIN')")
    with TestClient(app) as client:
        assert client.get('/api/demo/accounts').status_code == 503
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM memberships').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM cases').fetchone()[0] == 0
