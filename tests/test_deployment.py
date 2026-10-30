"""Deployment lifecycle checks use a fictional database and never call OpenAI."""
import logging
import time
from threading import Event, current_thread
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.agents import Handler, Registry
from backend.main import create_app
from backend.seed import seed


def test_proxy_health_is_public_and_keeps_existing_endpoint(tmp_path):
    app = create_app(tmp_path / 'health.sqlite3', agent_registry=Registry(), inbox_worker=False)
    with TestClient(app) as client:
        for path in ('/health', '/api/health'):
            response = client.get(path)
            assert response.status_code == 200
            assert response.json() == {'status': 'ok'}
        assert client.get('/api/session').status_code == 401


@pytest.mark.parametrize('setting', [None, '0', 'true'])
def test_api_worker_requires_explicit_one(tmp_path, monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv('SCHOOL_AGENT_RUN_WORKER', raising=False)
    else:
        monkeypatch.setenv('SCHOOL_AGENT_RUN_WORKER', setting)

    def forbidden(*args):
        raise AssertionError('Disabled API must not construct an AI worker')

    monkeypatch.setattr('backend.main.Worker', forbidden)
    app = create_app(tmp_path / 'disabled.sqlite3', agent_registry=Registry(), inbox_worker=False)
    with TestClient(app) as client:
        assert client.get('/api/health').status_code == 200


def test_api_worker_executes_persisted_job_and_stops_with_lifespan(tmp_path, monkeypatch):
    monkeypatch.setenv('SCHOOL_AGENT_RUN_WORKER', '1')
    path = tmp_path / 'worker.sqlite3'
    credentials = seed(path)
    registry = Registry()
    executed = Event()
    worker_threads = []

    class Result(BaseModel):
        summary: str

    def generate(snapshot):
        worker_threads.append(current_thread())
        executed.set()
        return {'summary': '[가상] 내부 워커 완료'}

    registry.register(Handler('REVIEW_SUPPORT', generate, Result, 'deployment-test', generation_mode='RULE'))
    app = create_app(path, agent_registry=registry, inbox_worker=False)
    headers = {'Authorization': 'Bearer ' + credentials['tokens']['admin'], 'Idempotency-Key': str(uuid4())}
    with TestClient(app) as client:
        response = client.post('/api/cases/demo-case/agent-runs', headers=headers, json={
            'expected_version': 1, 'purpose': 'REVIEW_SUPPORT',
            'input_refs': [{'resource_type': 'CASE', 'resource_id': 'demo-case', 'version': 1}],
        })
        assert response.status_code == 202
        assert executed.wait(5), 'Internal worker did not consume the queued job'
        deadline = time.monotonic() + 5
        while True:
            result = client.get('/api/agent-runs/' + response.json()['run_id'], headers=headers).json()
            if result['status'] == 'WAITING_REVIEW' or time.monotonic() >= deadline:
                break
            time.sleep(.02)
        assert result['status'] == 'WAITING_REVIEW'
        assert result['result'] == {'summary': '[가상] 내부 워커 완료'}
        assert result['attempts'] == 1
        assert client.get('/api/cases/demo-case', headers=headers).json()['version'] == 1
    assert worker_threads and all(not thread.is_alive() for thread in worker_threads)


def test_worker_loop_survives_exception_and_idle_wait_is_interruptible(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv('SCHOOL_AGENT_RUN_WORKER', '1')
    recovered, idle = Event(), Event()
    loop_threads = []
    received = []

    class FlakyWorker:
        def __init__(self, database, registry):
            received.append((database, registry))
            self.calls = 0

        def process_once(self):
            loop_threads.append(current_thread())
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError('fictional failure')
            if self.calls == 2:
                recovered.set()
                return True
            idle.set()
            return False

    monkeypatch.setattr('backend.main.Worker', FlakyWorker)
    app = create_app(tmp_path / 'recovery.sqlite3', agent_registry=Registry(), inbox_worker=False)
    with caplog.at_level(logging.ERROR), TestClient(app) as client:
        assert recovered.wait(5)
        assert idle.wait(5)
        assert client.get('/api/health').status_code == 200
    assert received == [(app.state.db, app.state.agent_registry)]
    assert 'agent_worker_failed type=RuntimeError' in caplog.text
    assert loop_threads and all(not thread.is_alive() for thread in loop_threads)
