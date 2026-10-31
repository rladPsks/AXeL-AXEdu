import pytest
from fastapi.testclient import TestClient

from agent.routing import route_case, recommend_roles
from agent.citations import with_source_metadata
from backend.agents import Registry
from backend.main import create_app
from backend.seed import seed
from backend.seed_support import seed_support
import backend.features.intake as intake


@pytest.mark.parametrize('text,expected', [
    ('생활지도 상황 확인', 'HEAD_LIFE_PE'),
    ('급식비 환불', 'ADMIN_CIVIL'),
    ('화장실 시설 고장', 'ADMIN_FACILITY'),
    ('학사일정 문의', 'HEAD_ACADEMIC_PLAN'),
    ('분야를 알 수 없는 질문', 'complaint_response_team'),
])
def test_three_explained_ranks_follow_duty_area(text, expected):
    routing = route_case('fact_check', text=text)
    ranks = routing['recommendations']
    assert [r['rank'] for r in ranks] == [1, 2, 3]
    assert len({r['role'] for r in ranks}) == 3
    assert ranks[0]['role'] == expected
    assert all(r['reason'] and r['sources'][0]['source_id'] == 'SCH-DUTY' for r in ranks)


def test_urgent_review_and_rag_are_distinct_from_duty_assignment():
    cls = {'urgency': 'HIGH'}
    routing = route_case('complex_or_sensitive', text='시설 안전사고', classification=cls)
    evidence = [{'source_id': 'manual', 'text': '절차 참고', 'pdf_page': 10}]
    ranks = recommend_roles(routing, text='시설 안전사고', classification=cls, evidence=evidence)
    assert ranks[0]['role'] == 'PRINCIPAL'
    assert ranks[0]['reference_evidence'][0]['source_id'] == evidence[0]['source_id']
    assert ranks[0]['reference_evidence'][0]['reference_reason']
    assert ranks[0]['sources'][0]['source_id'] != 'manual'


def test_registered_citations_preserve_saved_excerpt():
    rows = with_source_metadata([{'source_id': 'MOE-MANUAL-2026', 'text': '저장된 인용', 'pdf_page': 10}])
    assert rows[0]['title'] and rows[0]['uploaded_filename'].endswith('.pdf')
    law = with_source_metadata([{'source_id': 'LAW-SCHOOL-ACT'}])[0]
    assert law['official_url'].startswith('https://')
    assert rows[0]['text'] == '저장된 인용' and rows[0]['pdf_page'] == 10


@pytest.mark.parametrize('text,category,expected', [
    ('생활지도 상황 확인', 'EDU', 'life-head'),
    ('급식비 환불 확인', 'ADMIN', 'admin'),
    ('학사일정 문의', 'EDU', 'academic-head'),
])
def test_actual_intake_does_not_always_assign_deputy(tmp_path, monkeypatch, text, category, expected):
    path = tmp_path / 'routed.sqlite3'
    tokens = seed(path)['tokens']
    seed_support(path)
    monkeypatch.setattr(intake, 'classify_complaint', lambda _: {
        'category': category, 'nature': 'COMPLAINT', 'urgency': 'LOW', 'stage': 2,
        'is_informational': False, 'needs_fact_check': ['기록을 확인해 주세요.'],
        'infringement_flags': [], 'special_codes': [], 'summary_for_teacher': text,
        'classifier_mode': 'TEST',
    })
    monkeypatch.setattr(intake, 'retrieve_official_evidence', lambda *a, **kw: [
        {'source_id': 'MOE-MANUAL-2026', 'chunk_id': 'M-10-ROUTING', 'pdf_page': 10, 'text': '담당 협조', 'score': 10}])
    with TestClient(create_app(path, agent_registry=Registry(), inbox_worker=False)) as client:
        headers = {'Authorization': 'Bearer ' + tokens['admin'], 'Idempotency-Key': 'route'}
        response = client.post('/api/intakes', headers=headers, json={
            'channel': 'phone', 'complainant_name': '가상', 'complaint_type': text, 'raw_text': text})
        assert response.status_code == 201, response.text
        cid = response.json()['case_id']
        case = client.get(f'/api/cases/{cid}', headers=headers).json()
        assert case['owner_id'] == expected
        assert case['tasks'][0]['assignee_id'] == expected
        detail = client.get(f'/api/cases/{cid}/intake', headers=headers).json()
        citation = detail['routing']['recommendations'][0]['reference_evidence'][0]
        assert citation['uploaded_filename'] and citation['chunk_id'] == 'M-10-ROUTING'
        assert detail['workflow']['tools']['rag'][0]['pdf_page'] == 10


def test_review_persists_only_server_retrieved_citations(monkeypatch):
    import backend.openai_provider as provider
    from backend.agents import ProviderFailure
    from copy import deepcopy
    evidence = {'source_id': 'LAW-SCHOOL-ACT', 'chunk_id': 'test-law', 'article': '제35조', 'text': '테스트 근거'}
    monkeypatch.setattr(provider, 'retrieve_official_evidence', lambda *a, **kw: [evidence])
    monkeypatch.setattr(provider, 'translate_from_korean', lambda *a: None)
    adapter = provider.OpenAIAdapter('unused', 'unused')
    result = {'summary': '검토', 'observations': [], 'missing_information': [],
        'suggested_support': 'KEEP_REVIEWING', 'action_options': [], 'response_draft': '',
        'evidence_used': ['LAW-SCHOOL-ACT'], 'validation_checks': []}
    adapter._structured = lambda *a: deepcopy(result)
    snapshot = {'sources': [{'ref': {'resource_type': 'CASE', 'resource_id': 'case'},
        'data': {'intake': {'raw_text': '가상 민원', 'workflow': {}, 'classification': {}}}}]}
    stored = provider.StoredSupportReviewResult.model_validate(adapter.support_review(snapshot))
    assert stored.evidence_sources[0]['official_url'].startswith('https://')
    assert stored.evidence_sources[0]['chunk_id'] == 'test-law'
    result['evidence_used'] = ['invented-source']
    with pytest.raises(ProviderFailure):
        adapter.support_review(snapshot)
