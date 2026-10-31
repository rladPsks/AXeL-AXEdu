from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.seed import seed
from backend.seed_patterns import seed_patterns
from backend.mission import response_closure_guard

@pytest.fixture
def env(tmp_path):
    path=tmp_path/'mission.sqlite3'
    tokens=seed(path)['tokens']
    assert seed_patterns(path)==7
    assert seed_patterns(path)==0
    app=create_app(path,inbox_worker=False)
    with TestClient(app) as client:
        yield client,tokens,app

def headers(tokens,user='admin'):
    return {'Authorization':'Bearer '+tokens[user],'Idempotency-Key':str(uuid4())}

def test_pattern_context_and_access(env):
    client,tokens,app=env
    data=client.get('/api/school/complainant-patterns',headers=headers(tokens)).json()
    group=data['groups'][0]
    assert group['count']==7 and group['issue_count']==2 and group['repeat_candidate']
    assert '답변 전달 기록 없음' in group['cases'][2]['signals'][0]
    assert not any('답변 전달 기록 없음' in s for s in group['cases'][5]['signals'])
    assert 'compare_case_id' not in group['cases'][6]
    assert group['cases'][6]['signals'][0].startswith('새 사안')
    assert client.get('/api/school/complainant-patterns',headers=headers(tokens,'teacher')).status_code==403
    assert client.get('/api/school/complainant-patterns',headers=headers(tokens,'other-admin')).json()['groups']==[]
    history=client.get('/api/cases/demo-pattern-05/full-history',headers=headers(tokens))
    assert history.status_code==200,history.text
    assert any(e['source']=='자료 버전' for e in history.json())

def test_response_versions_delivery_closure_and_stale(env):
    client,tokens,app=env
    path='/api/cases/demo-pattern-01/work-products/RESPONSE'
    def post(url,body): return client.post(url,headers=headers(tokens),json={'expected_version':1,**body})
    with app.state.db.transaction() as db:
        assert response_closure_guard(db,None,'demo-pattern-01')
    saved=post(path,{'previous_revision':0,'content':{'text':'확인한 사실만 안내합니다.'},'reason':'작성'})
    assert saved.status_code==200,saved.text
    assert post(path,{'previous_revision':0,'content':{'text':'동시 수정'},'reason':'경합'}).status_code==409
    assert post(path+'/transition',{'revision':1,'action':'DELIVERED','reason':'미승인'}).status_code==409
    assert post(path+'/transition',{'revision':1,'action':'APPROVED','reason':'검토'}).status_code==200
    assert post(path+'/transition',{'revision':2,'action':'DELIVERED','reason':'시연상 학교 시스템 전달 확인'}).status_code==200
    with app.state.db.transaction() as db:
        assert not response_closure_guard(db,None,'demo-pattern-01')
        db.execute("UPDATE cases SET version=2 WHERE id='demo-pattern-01'")
    assert client.get(path,headers=headers(tokens)).json()['products'][0]['stale']
    history=client.get('/api/cases/demo-pattern-01/full-history',headers=headers(tokens)).json()
    assert any(e['action']=='RESPONSE_DELIVERED' for e in history)

def test_report_requires_current_external_decision(env):
    client,tokens,app=env
    base='/api/cases/demo-case'
    path=base+'/work-products/REPORT'
    report=client.get(path,headers=headers(tokens))
    assert report.status_code==200,report.text
    decision={'expected_version':1,'decision_type':'EXTERNAL_SUPPORT','reason':'학교 조치 후 전문지원 검토','target':'관할 교육지원청','route':'담당 부서 확인 후 제출','remaining_school_work':'학생 보호 및 사실 확인 계속','observations':[{'source_id':'demo-case','kind':'UNVERIFIED','detail':'외부 확인 필요'}],'input_refs':[{'resource_type':'CASE','resource_id':'demo-case','version':1}]}
    assert client.post(base+'/support-decisions',headers=headers(tokens),json=decision).status_code==201
    text=client.get(path,headers=headers(tokens)).json()['initial']['text']
    assert '학교 조치 후 전문지원 검토' in text
    assert client.post(path,headers=headers(tokens),json={'expected_version':2,'previous_revision':0,'content':{'text':text},'reason':'작성'}).status_code==200
    for revision,action in [(1,'APPROVED'),(2,'EXPORTED')]:
        response=client.post(path+'/transition',headers=headers(tokens),json={'expected_version':2,'revision':revision,'action':action,'reason':'검토 확인'})
        assert response.status_code==200,response.text
    assert response.json()['text']==text
    with app.state.db.transaction() as db: db.execute("UPDATE cases SET version=3 WHERE id='demo-case'")
    response=client.post(path+'/transition',headers=headers(tokens),json={'expected_version':3,'revision':3,'action':'EXPORTED','reason':'오래된 문서'})
    assert response.status_code==409


def test_approved_translation_is_used_in_new_analysis_snapshot(env):
    from backend.agents import snapshot,InputRef
    from backend.access import accessible_case
    client,tokens,app=env
    path='/api/cases/demo-pattern-01/work-products/TRANSLATION'
    assert client.post(path,headers=headers(tokens),json={'expected_version':1,'previous_revision':0,'content':{'text':'검토 완료된 한국어 번역','original':'Please confirm.','language':'en'},'reason':'원문 대조'}).status_code==200
    result=client.post(path+'/transition',headers=headers(tokens),json={'expected_version':1,'revision':1,'action':'APPROVED','reason':'날짜와 요구 대조 완료'})
    assert result.status_code==200 and result.json()['version']==2,result.text
    with app.state.db.transaction() as db:
        actor={'user_id':'admin','school_id':'demo-school','role':'ADMIN'}
        case=accessible_case(db,actor,'demo-pattern-01')
        data=snapshot(db,actor,case,[InputRef(resource_type='CASE',resource_id=case['id'],version=2)])
        language=data['sources'][0]['data']['intake']['workflow']['multilingual']
        assert language['translated_text_ko']=='검토 완료된 한국어 번역'
        assert language['review_status']=='APPROVED'
    assert not client.get(path,headers=headers(tokens)).json()['products'][0]['stale']


def test_tone_uses_saved_response_and_preserves_source_revision(env):
    from backend.agents import snapshot,InputRef
    from backend.access import accessible_case
    from backend.openai_provider import OpenAIAdapter
    client,tokens,app=env
    path='/api/cases/demo-pattern-01/work-products/RESPONSE'
    client.post(path,headers=headers(tokens),json={'expected_version':1,'previous_revision':0,'content':{'text':'확인 후 안내하겠습니다.'},'reason':'초안'})
    with app.state.db.transaction() as db:
        actor={'user_id':'admin','school_id':'demo-school','role':'ADMIN'}
        case=accessible_case(db,actor,'demo-pattern-01')
        data=snapshot(db,actor,case,[InputRef(resource_type='CASE',resource_id=case['id'],version=1)],'TONE_REWRITE')
    adapter=OpenAIAdapter('fake','test')
    adapter._structured=lambda *args: {'response_draft':'확인한 내용을 안내드리겠습니다.','changes':['존중 표현'],'meaning_checks':['새 약속 없음']}
    result=adapter.rewrite_tone(data)
    assert result['source_revision']==1 and result['original']=='확인 후 안내하겠습니다.'


def test_referral_recommendation_preserves_actual_locator_and_logs(env,monkeypatch):
    client,tokens,app=env
    def retrieve(query,**kwargs):
        assert kwargs['allowed_source_types']=={'official_manual','policy_plan'}
        return [{'source_id':'manual-test','title':'가상 매뉴얼','source_type':'official_manual','pdf_page':11,'text':'생활지도 관련 학교 공동 대응을 검토한다.','verification_status':'pending'}, {'source_id':'no-location','text':'인용 위치 없음'}]
    monkeypatch.setattr('agent.retrieval.retrieve',retrieve)
    path='/api/cases/demo-pattern-01/referral-evidence'
    result=client.post(path,headers=headers(tokens),json={'expected_version':1})
    assert result.status_code==200,result.text
    items=result.json()['items']
    assert len(items)==1 and items[0]['location']=='PDF 11쪽'
    assert items[0]['excerpt']=='생활지도 관련 학교 공동 대응을 검토한다.'
    assert items[0]['verification_status']=='pending' and not items[0]['external_support_mention']
    assert client.post(path,headers=headers(tokens,'teacher'),json={'expected_version':1}).status_code==403
    history=client.get('/api/cases/demo-pattern-01/full-history',headers=headers(tokens)).json()
    assert history[0]['action']=='REFERRAL_EVIDENCE_RECOMMENDED'
