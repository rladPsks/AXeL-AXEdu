import json
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.agents import Handler,ProviderFailure,Registry
from backend.comparison_review import ComparisonResult
from backend.main import create_app
from backend.openai_provider import OpenAIAdapter,create_registry
from backend.seed import seed
from backend.worker import Worker


def result(source='demo-case'):
    return {'summary':'[가상] 추가 확인이 필요한 재문의','findings':[{'category':'UNANSWERED_FOLLOWUP','assessment':'UNVERIFIED','detail':'[가상] 기록만으로 실제 미응답을 확정할 수 없음','source_ids':[source]}],
            'missing_information':['실제 답변 전달 증빙'],'follow_up_questions':['이전 답변을 누가 언제 전달했는지 확인하세요.']}


@pytest.fixture
def env(tmp_path):
    path=tmp_path/'review.sqlite3'
    creds=seed(path)
    registry=Registry()
    registry.register(Handler('COMPARE_CASES',lambda snapshot:result(),ComparisonResult,'comparison-test',generation_mode='RULE'))
    app=create_app(path,agent_registry=registry,inbox_worker=False)
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO cases(id,school_id,title,owner_id,status,version) VALUES ('prior','demo-school','[가상] 이전 접수','deputy','OPEN',1)")
        db.execute("INSERT INTO cases(id,school_id,title,owner_id,status,version) VALUES ('foreign','other-school','[가상] 타 학교','other-admin','OPEN',1)")
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','teacher')")
    with TestClient(app,raise_server_exceptions=False) as client:
        yield client,creds,app,registry


def auth(creds,user='admin',key=None):
    return {'Authorization':'Bearer '+creds['tokens'][user],'Idempotency-Key':key or str(uuid4())}


def prepare(client,creds,version=1,related_version=1,**extra):
    return client.post('/api/cases/demo-case/comparison-inputs',headers=auth(creds),json={'expected_version':version,'related_case_id':'prior','expected_related_version':related_version,
        'source_refs':[{'case_id':'demo-case','resource_type':'CASE','resource_id':'demo-case','version':version},{'case_id':'prior','resource_type':'CASE','resource_id':'prior','version':related_version}],**extra})


def start(client,creds,input_id,version=1,**extra):
    return client.post('/api/cases/demo-case/agent-runs',headers=auth(creds),json={'expected_version':version,'purpose':'COMPARE_CASES',
        'input_refs':[{'resource_type':'COMPARISON_INPUT','resource_id':input_id,'version':1}],**extra})


def save_review(client,creds,input_id,version=1,**extra):
    return client.post('/api/cases/demo-case/comparison-reviews',headers=auth(creds),json={'expected_version':version,'input_id':input_id,'reason':'[가상] 두 사건 원문 대조 완료','findings':result()['findings'],**extra})


def test_inputs_preserve_versions_and_scoped_sources_and_permissions(env):
    client,creds,app,_=env
    response=prepare(client,creds)
    assert response.status_code==201 and response.json()['version']==1
    saved=client.get('/api/cases/demo-case/comparison-inputs',headers=auth(creds)).json()[0]
    assert not saved['stale'] and saved['case_version']==saved['related_case_version']==1
    assert [source['data']['id'] for source in saved['sources']]==['demo-case','prior']
    assert client.get('/api/cases/demo-case/comparison-inputs',headers=auth(creds,'teacher')).status_code==403
    assert prepare(client,creds,related_case_id='foreign').status_code==404
    assert prepare(client,creds,source_refs=[{'case_id':'demo-case','resource_type':'CASE','resource_id':'demo-case','version':1}]*2).json()['code']=='COMPARISON_SOURCE_SCOPE'
    assert prepare(client,creds,related_version=2).json()['code']=='RELATED_VERSION_CONFLICT'
    with app.state.db.transaction() as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('DELETE FROM comparison_inputs')


def test_related_change_marks_run_stale_and_cannot_be_overridden(env):
    client,creds,app,registry=env
    input_id=prepare(client,creds).json()['comparison_input_id']
    run=start(client,creds,input_id).json()['run_id']
    assert Worker(app.state.db,registry).process_once()
    with app.state.db.transaction() as db:
        db.execute("UPDATE cases SET version=2 WHERE id='prior'")
    viewed=client.get('/api/agent-runs/'+run,headers=auth(creds)).json()
    assert viewed['stale'] and viewed['status']=='WAITING_REVIEW'
    assert start(client,creds,input_id).json()['code']=='STALE_COMPARISON_INPUT'
    accepted=client.post(f'/api/agent-runs/{run}/review',headers=auth(creds),json={'expected_version':1,'decision':'ACCEPT','reason':'[가상] 원문 대조','accept_stale':True})
    assert accepted.json()['code']=='STALE_COMPARISON_INPUT'
    assert save_review(client,creds,input_id).json()['code']=='STALE_COMPARISON_INPUT'


def test_school_policy_change_requires_new_comparison_inputs(env):
    client,creds,app,registry=env
    input_id=prepare(client,creds).json()['comparison_input_id']
    assert client.put('/api/school/repeat-settings',headers=auth(creds),json={'expected_settings_version':1,'window_days':20,'minimum_count':4}).status_code==200
    assert client.get('/api/cases/demo-case/comparison-inputs',headers=auth(creds)).json()[0]['stale']
    assert save_review(client,creds,input_id).json()['code']=='STALE_COMPARISON_INPUT'


def test_model_review_does_not_create_human_record_and_human_apply_keeps_owner(env):
    client,creds,app,registry=env
    input_id=prepare(client,creds).json()['comparison_input_id']
    run=start(client,creds,input_id).json()['run_id']
    assert Worker(app.state.db,registry).process_once()
    assert save_review(client,creds,input_id,reviewed_run_id=run).json()['code']=='AGENT_RESULT_NOT_READY'
    assert client.post(f'/api/agent-runs/{run}/review',headers=auth(creds),json={'expected_version':1,'decision':'ACCEPT','reason':'[가상] AI 제안 검토'}).status_code==200
    assert client.get('/api/cases/demo-case/comparison-reviews',headers=auth(creds)).json()==[]
    response=save_review(client,creds,input_id,reviewed_run_id=run)
    assert response.status_code==201 and response.json()['version']==2
    review=client.get('/api/comparison-reviews/'+response.json()['comparison_review_id'],headers=auth(creds)).json()
    assert not review['stale'] and review['reviewed_ai']['run_id']==run
    assert review['input']['sources'][1]['data']['id']=='prior'
    assert client.get('/api/cases/demo-case',headers=auth(creds)).json()['owner_id']=='admin'
    assert client.get('/api/cases/prior',headers=auth(creds)).json()['version']==1
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM support_decisions').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM case_relation_events').fetchone()[0]==0


def test_human_snapshot_idempotency_citations_and_audit_rollback(env,monkeypatch):
    client,creds,app,_=env
    input_id=prepare(client,creds).json()['comparison_input_id']
    assert save_review(client,creds,input_id,findings=[{**result()['findings'][0],'source_ids':['invented']}]).json()['code']=='INVALID_COMPARISON_CITATION'
    def broken(*args,**kwargs):raise RuntimeError('audit failed')
    with monkeypatch.context() as patch:
        patch.setattr('backend.commands.audit',broken)
        assert save_review(client,creds,input_id).status_code==500
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM comparison_reviews').fetchone()[0]==0
        assert db.execute("SELECT version FROM cases WHERE id='demo-case'").fetchone()[0]==1
    payload={'expected_version':1,'input_id':input_id,'reason':'[가상] 직접 검토','findings':result()['findings']}
    headers=auth(creds,key='review-once')
    first=client.post('/api/cases/demo-case/comparison-reviews',headers=headers,json=payload)
    assert first.status_code==201
    assert client.post('/api/cases/demo-case/comparison-reviews',headers=headers,json=payload).json()==first.json()
    with app.state.db.transaction() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM comparison_reviews')


def test_support_decision_inherits_other_case_dependency_for_report(env):
    client,creds,app,_=env
    input_id=prepare(client,creds).json()['comparison_input_id']
    review=save_review(client,creds,input_id).json()['comparison_review_id']
    decision=client.post('/api/cases/demo-case/support-decisions',headers=auth(creds),json={
        'expected_version':2,'decision_type':'KEEP_REVIEWING','reason':'[가상] 비교 후 지원 판단','target':'학교 대응팀','route':'추가 확인','remaining_school_work':'답변 전달 확인',
        'input_refs':[{'resource_type':'COMPARISON_REVIEW','resource_id':review,'version':1}],
        'observations':[{'source_id':review,'kind':'UNVERIFIED','detail':'추가 증빙 확인 필요'}]})
    assert decision.status_code==201
    decision_id=decision.json()['decision_id']
    path=f'/api/support-decisions/{decision_id}/snapshot?expected_case_version=3'
    assert client.get(path,headers=auth(creds)).status_code==200
    with app.state.db.transaction() as db:db.execute("UPDATE cases SET version=2 WHERE id='prior'")
    assert client.get('/api/support-decisions/'+decision_id,headers=auth(creds)).json()['stale']
    assert client.get(path,headers=auth(creds)).json()['code']=='STALE_SUPPORT_DECISION'
    assert client.get('/api/comparison-reviews/'+review,headers=auth(creds,'teacher')).status_code==403


def test_invalid_plugin_citations_are_not_persisted_as_a_success(env):
    client,creds,app,registry=env
    registry.handlers['COMPARE_CASES']=Handler('COMPARE_CASES',lambda snapshot:result('invented'),ComparisonResult,'bad-citation',generation_mode='RULE')
    run=start(client,creds,prepare(client,creds).json()['comparison_input_id']).json()['run_id']
    assert Worker(app.state.db,registry).process_once()
    viewed=client.get('/api/agent-runs/'+run,headers=auth(creds)).json()
    assert viewed['status']=='FAILED' and viewed['error']['code']=='INVALID_CITATION' and viewed['result'] is None


def test_openai_comparison_uses_original_citations_schema_and_refusal_handling():
    source={'ref':{'resource_id':'input','resource_type':'COMPARISON_INPUT'},'data':{'sources':[{'ref':{'resource_id':'demo-case'}}]}}
    snapshot={'sources':[source]}
    calls=[]
    reply=SimpleNamespace(status='completed',output_parsed=result())
    def parse(**kwargs):calls.append(kwargs);return reply
    adapter=OpenAIAdapter('test-not-a-key','configured-model',SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    assert adapter.compare_cases(snapshot)['findings'][0]['source_ids']==['demo-case']
    assert calls[0]['text_format'] is ComparisonResult and calls[0]['store'] is False and 'tools' not in calls[0]
    reply.output_parsed=result('invented')
    with pytest.raises(ProviderFailure,match='비교 입력'):adapter.compare_cases(snapshot)
    reply.output_parsed=None
    with pytest.raises(ProviderFailure):adapter.compare_cases(snapshot)
    registry=create_registry(key='test-not-a-key',model='configured-model')
    assert registry.handlers['COMPARE_CASES'].generation_mode=='MODEL'


def test_real_sdk_comparison_transport_without_network():
    import httpx2
    import openai
    requests=[]
    def transport(request):
        requests.append(request)
        return httpx2.Response(200,json={'id':'resp_comparison_test','object':'response','created_at':0,'status':'completed','model':'configured-model','error':None,'incomplete_details':None,
          'output':[{'id':'msg_comparison','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':json.dumps(result()),'annotations':[]}]}],
          'parallel_tool_calls':True,'tool_choice':'auto','tools':[]})
    with openai.OpenAI(api_key='test-not-a-key',http_client=httpx2.Client(transport=httpx2.MockTransport(transport)),max_retries=0) as sdk:
        snapshot={'sources':[{'ref':{'resource_type':'COMPARISON_INPUT','resource_id':'saved-input'},'data':{'sources':[{'ref':{'resource_id':'demo-case'}}]}}]}
        value=OpenAIAdapter(None,'configured-model',sdk).compare_cases(snapshot)
    assert value['findings'][0]['source_ids']==['demo-case'] and len(requests)==1
    sent=json.loads(requests[0].content)
    assert requests[0].url.path=='/v1/responses' and sent['store'] is False and sent['max_output_tokens']==4200
    assert sent['text']['format']['strict'] is True and sent['text']['format']['type']=='json_schema'


def test_completed_cross_case_result_and_review_are_not_available_after_role_change(env):
    client,creds,app,registry=env
    input_id=prepare(client,creds).json()['comparison_input_id']
    run=start(client,creds,input_id).json()['run_id']
    assert Worker(app.state.db,registry).process_once()
    review_id=save_review(client,creds,input_id).json()['comparison_review_id']
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','admin')")
        db.execute("UPDATE memberships SET role='TEACHER' WHERE user_id='admin' AND school_id='demo-school'")
    assert client.get('/api/cases/demo-case/agent-runs',headers=auth(creds)).json()==[]
    assert client.get('/api/agent-runs/'+run,headers=auth(creds)).status_code==403
    assert client.get('/api/comparison-reviews/'+review_id,headers=auth(creds)).status_code==403


def test_support_decision_also_tracks_comparison_used_indirectly_by_reviewed_ai(env):
    client,creds,app,registry=env
    from backend.openai_provider import SupportReviewResult
    registry.register(Handler('REVIEW_SUPPORT',lambda snapshot:{'summary':'[가상] 비교 참고 지원 제안','observations':[],
      'missing_information':['전달 증빙'],'suggested_support':'KEEP_REVIEWING','action_options':['학교 추가 확인'],
      'response_draft':'','validation_checks':[],'evidence_used':[]},SupportReviewResult,'support-test',generation_mode='RULE'))
    review=save_review(client,creds,prepare(client,creds).json()['comparison_input_id']).json()['comparison_review_id']
    run=client.post('/api/cases/demo-case/agent-runs',headers=auth(creds),json={'expected_version':2,'purpose':'REVIEW_SUPPORT',
        'input_refs':[{'resource_type':'COMPARISON_REVIEW','resource_id':review,'version':1}]}).json()['run_id']
    assert Worker(app.state.db,registry).process_once()
    assert client.post(f'/api/agent-runs/{run}/review',headers=auth(creds),json={'expected_version':2,'decision':'ACCEPT','reason':'[가상] 교차 검토 참고 확인'}).status_code==200
    response=client.post('/api/cases/demo-case/support-decisions',headers=auth(creds),json={'expected_version':2,'decision_type':'KEEP_REVIEWING','reason':'[가상] 검토한 제안 참고','target':'학교 대응팀','route':'추가 확인','remaining_school_work':'전달 확인',
      'input_refs':[{'resource_type':'CASE','resource_id':'demo-case','version':2}],'observations':[{'source_id':'demo-case','kind':'UNVERIFIED','detail':'추가 정보 필요'}],'reviewed_run_id':run})
    assert response.status_code==201
    path='/api/support-decisions/'+response.json()['decision_id']
    assert client.get(path,headers=auth(creds)).json()['stale'] is False
    with app.state.db.transaction() as db:db.execute("UPDATE cases SET version=2 WHERE id='prior'")
    assert client.get(path,headers=auth(creds)).json()['stale'] is True
