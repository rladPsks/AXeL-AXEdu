import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.agents import Handler, ProviderFailure, Registry
from backend.main import create_app
from backend.openai_provider import OpenAIAdapter, SupportReviewResult
from backend.seed import seed
from backend.worker import Worker


def review_result():
    return dict(summary='fixture', observations=[], missing_information=[],
                suggested_support='KEEP_REVIEWING', action_options=[],
                response_draft='', validation_checks=[], evidence_used=[])


@pytest.fixture
def intake_env(tmp_path, monkeypatch):
    monkeypatch.setattr('backend.features.intake.classify_complaint', lambda text: {
        'nature': 'INFO_REQUEST', 'urgency': 'LOW', 'needs_fact_check': [],
        'is_informational': True, 'stage': 1, 'summary_for_teacher': 'fictional',
    })
    path = tmp_path / 'regression.sqlite3'
    tokens = seed(path)['tokens']
    registry = Registry()
    registry.register(Handler('REVIEW_SUPPORT', lambda snapshot: review_result(),
                              SupportReviewResult, 'fixture', generation_mode='RULE'))
    app = create_app(path, agent_registry=registry, inbox_worker=False)
    def auth(user='admin'):
        return {'Authorization': 'Bearer ' + tokens[user], 'Idempotency-Key': str(uuid4())}
    with TestClient(app) as client:
        def intake(user='admin'):
            response = client.post('/api/intakes', headers=auth(user), json={
                'channel': 'phone', 'complainant_name': 'fictional-shared-name',
                'complaint_type': 'fixture', 'raw_text': 'fictional confidential history',
            })
            assert response.status_code == 201
            return response.json()['case_id']
        yield client, app, registry, auth, intake


def test_intake_history_checks_access_on_creation_read_and_snapshot(intake_env):
    client, app, registry, auth, intake = intake_env
    prior = intake()
    assert client.get('/api/cases/' + prior, headers=auth('outsider')).status_code == 403
    other = intake('outsider')
    def history(case_id, user):
        return client.get(f'/api/cases/{case_id}/intake', headers=auth(user)).json()['workflow']['tools']['history']
    assert history(other, 'outsider') == []
    current = intake()
    assert prior in {row['case_id'] for row in history(current, 'admin')}
    with app.state.db.transaction() as db:
        db.execute('INSERT INTO case_participants(case_id,user_id) VALUES (?,?)', (current, 'outsider'))
    # Joining the new case must not grant access to copied history from another case.
    assert prior not in {row['case_id'] for row in history(current, 'outsider')}
    started = client.post(f'/api/cases/{current}/agent-runs', headers=auth('outsider'), json={
        'expected_version': 1, 'purpose': 'REVIEW_SUPPORT',
        'input_refs': [{'resource_type': 'CASE', 'resource_id': current, 'version': 1}],
    })
    assert started.status_code == 202
    with app.state.db.transaction() as db:
        saved = json.loads(db.execute('SELECT snapshot FROM agent_runs WHERE id=?', (started.json()['run_id'],)).fetchone()[0])
    context = saved['sources'][0]['data']['intake']
    assert 'workflow_json' not in context
    assert prior not in {row['case_id'] for row in context['workflow']['tools']['history']}
    with app.state.db.transaction() as db:
        db.execute('UPDATE cases SET version=version+1 WHERE id=?', (prior,))
    assert prior not in {row['case_id'] for row in history(current, 'admin')}


def test_queued_history_rechecks_role_and_version_before_generation(intake_env):
    client, app, registry, auth, intake = intake_env
    prior, current = intake(), intake()
    response = client.post(f'/api/cases/{current}/agent-runs', headers=auth(), json={
        'expected_version': 1, 'purpose': 'REVIEW_SUPPORT',
        'input_refs': [{'resource_type': 'CASE', 'resource_id': current, 'version': 1}],
    })
    assert response.status_code == 202
    run_id = response.json()['run_id']
    with app.state.db.transaction() as db:
        db.execute("UPDATE memberships SET role='TEACHER' WHERE user_id='admin' AND school_id='demo-school'")
        db.execute("DELETE FROM case_participants WHERE case_id=? AND user_id='admin'", (prior,))
    assert client.get('/api/agent-runs/' + run_id, headers=auth()).status_code == 403
    with app.state.db.transaction() as db:
        db.execute("UPDATE memberships SET role='ADMIN' WHERE user_id='admin' AND school_id='demo-school'")
        db.execute('UPDATE cases SET version=version+1 WHERE id=?', (prior,))
    assert client.get('/api/agent-runs/' + run_id, headers=auth()).status_code == 409
    assert Worker(app.state.db, registry).process_once()
    with app.state.db.transaction() as db:
        run = db.execute('SELECT status,error FROM agent_runs WHERE id=?', (run_id,)).fetchone()
    assert run['status'] == 'FAILED'
    assert json.loads(run['error'])['code'] == 'ACCESS_REVOKED'


def test_official_citations_are_limited_to_actual_retrieval(monkeypatch):
    monkeypatch.setattr('backend.openai_provider.retrieve_official_evidence',
                        lambda *args, **kwargs: [{'source_id': 'official-1', 'text': 'fixture'}])
    value = review_result()
    value['evidence_used'] = ['official-1']
    client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs:
        SimpleNamespace(status='completed', output_parsed=value)))
    adapter = OpenAIAdapter(None, 'fixture', client)
    snapshot = {'sources': [{'ref': {'resource_type': 'CASE', 'resource_id': 'case'},
                             'data': {'intake': {'raw_text': 'fictional'}}}]}
    assert adapter.support_review(snapshot)['evidence_used'] == ['official-1']
    for invalid in ('NONEXISTENT', 'case'):
        value['evidence_used'] = [invalid]
        with pytest.raises(ProviderFailure) as exc:
            adapter.support_review(snapshot)
        assert exc.value.code == 'INVALID_CITATION'


def test_classifier_reads_env_loaded_after_import(tmp_path, monkeypatch):
    import llm_client
    from backend.envfile import load_env_file
    for name in ('OPENAI_API_KEY', 'OPENAI_MODEL', 'LLM_API_KEY', 'LLM_MODEL', 'LLM_BASE_URL', 'OPENAI_BASE_URL'):
        monkeypatch.delenv(name, raising=False)
    assert not llm_client.configured()
    file = tmp_path / '.env'
    file.write_text('OPENAI_API_KEY=fake-key-never-sent\nOPENAI_MODEL=fixture-model\n', encoding='utf-8')
    monkeypatch.setenv('SCHOOL_AGENT_LOAD_DOTENV', '1')
    # Register cleanup for keys the loader writes directly to os.environ.
    monkeypatch.setenv('OPENAI_API_KEY', '')
    monkeypatch.delenv('OPENAI_API_KEY')
    monkeypatch.setenv('OPENAI_MODEL', '')
    monkeypatch.delenv('OPENAI_MODEL')
    load_env_file(file)
    requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return json.dumps({'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': '{"ok": true}'}]}]}).encode()
    def urlopen(request, **kwargs):
        requests.append(request)
        return Response()
    monkeypatch.setattr(llm_client.urllib.request, 'urlopen', urlopen)
    assert llm_client.configured()
    assert llm_client.chat_json(system='fixture', user='fixture') == {'ok': True}
    assert json.loads(requests[0].data)['model'] == 'fixture-model'
    assert requests[0].get_header('Authorization') == 'Bearer fake-key-never-sent'
