import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.agents import Registry
from backend.main import create_app
from backend.seed import seed
from backend.seed_patterns import seed_patterns


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / 'referral.sqlite3'
    tokens = seed(path)['tokens']
    seed_patterns(path)
    def retrieve(query, **kwargs):
        assert '학교 민원 대응 이관 교육지원청 지원' not in query
        return [
            {'source_id':'related','title':'생활지도 매뉴얼','source_type':'official_manual','pdf_page':10,
             'text':'생활지도 사안은 학교에서 사실을 확인하고 공동 대응한다.','verification_status':'verified'},
            {'source_id':'unrelated','title':'급식비 환불 지침','source_type':'policy_plan','pdf_page':22,
             'text':'급식비 환불 신청서는 행정실에서 수납 내역을 확인한다.','verification_status':'verified'},
        ]
    monkeypatch.setattr('agent.retrieval.retrieve', retrieve)
    app = create_app(path, agent_registry=Registry(), inbox_worker=False)
    with TestClient(app) as client:
        yield client, tokens, app


def h(tokens):
    return {'Authorization':'Bearer '+tokens['admin'], 'Idempotency-Key':str(uuid4())}


def decide(client,tokens,version=1,supersedes=None):
    return client.post('/api/cases/demo-pattern-01/support-decisions',headers=h(tokens),json={
        'expected_version':version,'decision_type':'EXTERNAL_SUPPORT','reason':'학생 보호 지원 범위 확인 필요',
        'target':'관할 교육지원청 담당 부서 확인 필요','route':'학교 검토 후 지원 문의',
        'remaining_school_work':'학교 사실 확인과 학생 보호 계속',
        'observations':[{'source_id':'demo-pattern-01','kind':'UNVERIFIED','detail':'외부 지원 필요성 추가 확인'}],
        'input_refs':[{'resource_type':'CASE','resource_id':'demo-pattern-01','version':version}],
        'supersedes_id':supersedes,
    })


def test_report_uses_only_case_related_references_and_stays_a_draft(env):
    client,tokens,app=env
    base='/api/cases/demo-pattern-01'
    result=client.post(base+'/referral-evidence',headers=h(tokens),json={'expected_version':1}).json()
    assert [e['source_id'] for e in result['items']]==['related']
    data=client.get(base+'/work-products/REPORT',headers=h(tokens)).json()
    assert [e['source_id'] for e in data['evidence']]==['related']
    assert '출처 ID: related' in data['initial']['text']
    assert '급식비' not in data['initial']['text']
    assert '이관 여부 미확정' in data['initial']['text'] and data['products']==[]
    assert data['decision'] is None


def test_approved_report_can_be_revised_and_only_new_saved_text_is_exported(env):
    client,tokens,app=env
    decision=decide(client,tokens)
    assert decision.status_code==201
    path='/api/cases/demo-pattern-01/work-products/REPORT'
    def save(revision,text):
        return client.post(path,headers=h(tokens),json={'expected_version':2,'previous_revision':revision,
            'content':{'text':text},'reason':'검토 본문 작성'})
    def transition(revision,action):
        return client.post(path+'/transition',headers=h(tokens),json={'expected_version':2,'revision':revision,
            'action':action,'reason':'해당 민원의 본문과 지원 판단 대조'})
    assert save(0,'첫 검토 초안').status_code==200
    assert transition(1,'APPROVED').status_code==200
    assert save(2,'수정한 현재 본문').status_code==200
    assert transition(3,'EXPORTED').status_code==409
    assert transition(3,'APPROVED').status_code==200
    exported=transition(4,'EXPORTED')
    assert exported.status_code==200 and exported.json()['text']=='수정한 현재 본문'
    product=client.get(path,headers=h(tokens)).json()['products'][0]
    assert product['decision_id']==decision.json()['decision_id']


def test_unfinished_citation_cannot_be_approved_and_new_decision_regenerates_draft(env):
    client,tokens,app=env
    first=decide(client,tokens).json()
    path='/api/cases/demo-pattern-01/work-products/REPORT'
    assert client.post(path,headers=h(tokens),json={'expected_version':2,'previous_revision':0,
        'content':{'text':'학교 조치와 해당 민원의 연결 근거: [담당자 작성 필요]'},'reason':'검토 중'}).status_code==200
    result=client.post(path+'/transition',headers=h(tokens),json={'expected_version':2,'revision':1,
        'action':'APPROVED','reason':'미작성 상태 검증'})
    assert result.status_code==409 and result.json()['code']=='REPORT_INCOMPLETE'
    with app.state.db.transaction() as db:
        db.execute("UPDATE cases SET version=3 WHERE id='demo-pattern-01'")
    data=client.get(path,headers=h(tokens)).json()
    assert data['products'][0]['stale'] and data['decision']['stale']
    assert '학생 보호 지원 범위 확인 필요' not in data['initial']['text']
    assert '관리자 판단 미등록' in data['initial']['text']
