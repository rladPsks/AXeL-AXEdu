import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.agents import Registry
from backend.main import create_app
from backend.seed import seed
from backend.seed_support import seed_support
from backend.seed_multilingual import seed_multilingual
import backend.features.intake as feature


@pytest.fixture
def env(tmp_path):
    path = tmp_path / 'rag.sqlite3'
    tokens = seed(path)['tokens']
    seed_support(path)
    seed_multilingual(path)
    app = create_app(path, agent_registry=Registry(), inbox_worker=False)
    with TestClient(app) as client:
        yield client, app, tokens


def headers(tokens, user='admin', key=None):
    return {'Authorization': 'Bearer '+tokens[user], 'Idempotency-Key': key or str(uuid4())}


def test_opening_fixture_searches_real_corpus_with_korean_text_and_provenance(env):
    client, app, tokens = env
    for lang in ('zh', 'mn', 'ru'):
        cid = 'demo-multilingual-'+lang
        item = client.get(f'/api/cases/{cid}/intake', headers=headers(tokens)).json()
        tools = item['workflow']['tools']
        assert tools['rag_search']['status'] == 'FOUND'
        assert tools['rag_search']['mode'] == 'ON_VIEW_RETRIEVAL'
        assert item['workflow']['multilingual']['translated_text_ko'] in tools['rag_search']['query']
        assert tools['rag'] and all(e['source_id'] and e['title'] and (e.get('official_url') or e.get('uploaded_filename')) for e in tools['rag'])
        assert item['routing']['recommendations'][0]['reference_evidence']
        assert item['classification']['classifier_mode'] == 'DEMO_FIXTURE'
        # Viewing search results must not alter the original, approval or assignment.
        with app.state.db.transaction() as db:
            saved = json.loads(db.execute('SELECT workflow_json FROM case_intakes WHERE case_id=?', (cid,)).fetchone()[0])
            assert saved['tools']['rag'] == []
            assert saved['multilingual']['review_status'] == 'DRAFT'


def test_rag_refresh_is_persisted_audited_and_retry_safe(env):
    client, app, tokens = env
    cid = 'demo-multilingual-mn'
    url = f'/api/cases/{cid}/intake/rag-search'
    h = headers(tokens, key='rag-refresh')
    before = client.get(f'/api/cases/{cid}', headers=h).json()
    body = {'expected_version': before['version']}
    first = client.post(url, headers=h, json=body)
    assert first.status_code == 200 and first.json()['evidence_count'] > 0
    assert client.post(url, headers=h, json=body).json() == first.json()
    assert client.post(url, headers=headers(tokens), json=body).status_code == 409
    after = client.get(f'/api/cases/{cid}', headers=h).json()
    assert after['owner_id'] == before['owner_id'] and after['tasks'] == before['tasks']
    assert after['version'] == before['version']+1
    with app.state.db.transaction() as db:
        saved = json.loads(db.execute('SELECT workflow_json FROM case_intakes WHERE case_id=?', (cid,)).fetchone()[0])
        assert saved['tools']['rag'] and saved['tools']['rag_search']['status'] == 'FOUND'
        assert db.execute("SELECT count(*) FROM audit_events WHERE case_id=? AND action='INTAKE_RAG_SEARCHED'", (cid,)).fetchone()[0] == 1


def test_no_match_and_permission_denial_are_distinct(env, monkeypatch):
    client, app, tokens = env
    calls = []
    def empty(query, **kwargs):
        calls.append(query)
        return []
    monkeypatch.setattr(feature, 'retrieve_official_evidence', empty)
    url = '/api/cases/demo-multilingual-zh/intake'
    assert client.get(url, headers=headers(tokens, 'other-admin')).status_code == 404
    assert client.post(url+'/rag-search', headers=headers(tokens, 'teacher'), json={'expected_version': 1}).status_code == 403
    assert calls == []
    item = client.get(url, headers=headers(tokens)).json()
    assert item['workflow']['tools']['rag'] == []
    assert item['workflow']['tools']['rag_search']['status'] == 'NO_MATCH'


def test_changed_translation_replaces_saved_search_context(env):
    client, app, tokens = env
    cid = 'demo-multilingual-zh'
    url = f'/api/cases/{cid}/intake'
    assert client.post(url+'/rag-search', headers=headers(tokens), json={'expected_version': 1}).status_code == 200
    with app.state.db.transaction() as db:
        workflow = json.loads(db.execute('SELECT workflow_json FROM case_intakes WHERE case_id=?',(cid,)).fetchone()[0])
        workflow['multilingual'].update(translated_text_ko='학교폭력 피해학생 보호와 상담을 요청합니다.', review_status='APPROVED')
        db.execute('UPDATE case_intakes SET workflow_json=? WHERE case_id=?',(json.dumps(workflow,ensure_ascii=False),cid))
    item = client.get(url, headers=headers(tokens)).json()
    assert '학교폭력 피해학생' in item['workflow']['tools']['rag_search']['query']
    assert item['workflow']['tools']['rag_search']['mode'] == 'ON_VIEW_RETRIEVAL'
