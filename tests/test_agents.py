import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.agents import Handler, ProviderFailure, Registry, require_usable_result
from backend.commands import mutate
from backend.main import create_app
from backend.models import Command
from backend.openai_provider import OpenAIAdapter, SupportReviewResult, create_registry
from backend.seed import seed
from backend.worker import Worker


class Result(BaseModel):
    summary: str


def auth(creds, user='admin', key=None):
    return {'Authorization':'Bearer '+creds['tokens'][user], 'Idempotency-Key':key or str(uuid4())}


def start(client,creds,user='admin',version=1,**extra):
    return client.post('/api/cases/demo-case/agent-runs',headers=auth(creds,user),json={
        'expected_version':version,'purpose':'REVIEW_SUPPORT',
        'input_refs':[{'resource_type':'CASE','resource_id':'demo-case','version':version}],**extra})


@pytest.fixture
def env(tmp_path):
    path=tmp_path/'runs.sqlite3'
    creds=seed(path)
    registry=Registry()
    registry.register(Handler('REVIEW_SUPPORT',lambda snapshot:{'summary':'[가상] 검토 결과'},Result,'test-v1',generation_mode='RULE'))
    app=create_app(path,agent_registry=registry)
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','teacher')")
    with TestClient(app,raise_server_exceptions=False) as client:
        yield client,creds,app,registry


def test_queue_worker_review_and_domain_application_are_separate(env):
    client,creds,app,registry=env
    response=start(client,creds)
    assert response.status_code==202
    run_id=response.json()['run_id']
    assert response.json()['version']==1
    assert Worker(app.state.db,registry).process_once()
    result=client.get(f'/api/agent-runs/{run_id}',headers=auth(creds)).json()
    assert result['status']=='WAITING_REVIEW' and result['generation_mode']=='RULE'
    assert result['result']=={'summary':'[가상] 검토 결과'} and not result['stale']
    with app.state.db.transaction() as db:
        assert db.execute('SELECT version FROM cases').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM audit_events').fetchone()[0]==1
    reviewed=client.post(f'/api/agent-runs/{run_id}/review',headers=auth(creds),json={'expected_version':1,'decision':'ACCEPT','reason':'[가상] 원문 대조 완료'})
    assert reviewed.status_code==200 and reviewed.json()['version']==1
    # A/B apply a proposal only inside their own versioned domain command.
    router=APIRouter()
    @router.post('/api/cases/{case_id}/apply-test')
    def apply(case_id:str,body:Command,request:Request):
        def operation(db,actor,case):
            value=require_usable_result(db,actor,case,run_id,'REVIEW_SUPPORT')
            db.execute('UPDATE cases SET title=? WHERE id=?',(value['summary'],case_id))
            return {'applied_run_id':run_id}
        return mutate(request,case_id,body,'RESULT_APPLIED',operation)
    app.include_router(router)
    assert client.post('/api/cases/demo-case/apply-test',headers=auth(creds),json={'expected_version':1}).json()['version']==2
    stale=client.post('/api/cases/demo-case/apply-test',headers=auth(creds),json={'expected_version':2})
    assert stale.status_code==409 and stale.json()['code']=='STALE_AGENT_RESULT'
    with app.state.db.transaction() as db:
        notes=[json.loads(row[0]) for row in db.execute("SELECT detail FROM agent_run_events WHERE step='reviewed'")]
        assert notes[0]['reason']=='[가상] 원문 대조 완료'


def test_start_idempotency_and_missing_handler(env):
    client,creds,app,registry=env
    body={'expected_version':1,'purpose':'REVIEW_SUPPORT','input_refs':[{'resource_type':'CASE','resource_id':'demo-case','version':1}]}
    headers=auth(creds,key='one-run')
    first=client.post('/api/cases/demo-case/agent-runs',headers=headers,json=body)
    repeated=client.post('/api/cases/demo-case/agent-runs',headers=headers,json=body)
    assert first.status_code==repeated.status_code==202 and first.json()==repeated.json()
    assert start(client,creds,purpose='UNKNOWN').status_code==503
    assert start(client,creds,input_refs=[{'resource_type':'CASE','resource_id':'other','version':1}]).status_code==422
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM agent_runs').fetchone()[0]==1


def test_concurrent_workers_do_not_execute_same_claim(env):
    client,creds,app,registry=env
    start(client,creds)
    with ThreadPoolExecutor(max_workers=2) as pool:
        workers=[Worker(app.state.db,registry),Worker(app.state.db,registry)]
        outcomes=list(pool.map(lambda worker:worker.process_once(),workers))
    assert sorted(outcomes)==[False,True]
    with app.state.db.transaction() as db:
        assert db.execute('SELECT attempts FROM agent_runs').fetchone()[0]==1


def test_expired_lease_recovers_and_old_result_is_fenced(env):
    client,creds,app,registry=env
    run_id=start(client,creds).json()['run_id']
    clock=[100.0]
    first=Worker(app.state.db,registry,lease_seconds=10,clock=lambda:clock[0])
    old=first._claim()
    clock[0]=120
    second=Worker(app.state.db,registry,lease_seconds=10,clock=lambda:clock[0])
    current=second._claim()
    assert current['id']==old['id'] and current['lease_token']!=old['lease_token']
    first._finish(old,result={'summary':'old result'})
    second._finish(current,result={'summary':'new result'})
    result=client.get(f'/api/agent-runs/{run_id}',headers=auth(creds)).json()
    assert result['result']['summary']=='new result' and result['attempts']==2


def test_heartbeat_extends_lease_and_prevents_premature_recovery(env):
    client,creds,app,registry=env
    start(client,creds)
    clock=[100.0]
    worker=Worker(app.state.db,registry,lease_seconds=10,clock=lambda:clock[0])
    job=worker._claim()
    clock[0]=105
    worker._heartbeat(job)
    clock[0]=112
    assert Worker(app.state.db,registry,clock=lambda:clock[0])._claim() is None
    worker._finish(job,result={'summary':'heartbeat protected result'})


def test_handler_configuration_change_does_not_run_new_prompt_on_old_snapshot(env):
    client,creds,app,registry=env
    run_id=start(client,creds).json()['run_id']
    registry.handlers['REVIEW_SUPPORT']=Handler('REVIEW_SUPPORT',lambda _:pytest.fail('must not call'),Result,'new-version',generation_mode='RULE')
    Worker(app.state.db,registry).process_once()
    result=client.get(f'/api/agent-runs/{run_id}',headers=auth(creds)).json()
    assert result['status']=='FAILED' and result['error']['code']=='HANDLER_CHANGED'


def test_retry_bound_and_redacted_errors(env):
    client,creds,app,registry=env
    def unavailable(snapshot):
        raise ProviderFailure('TEMPORARY','연결 재시도 필요',True)
    registry.handlers['REVIEW_SUPPORT']=Handler('REVIEW_SUPPORT',unavailable,Result,'test-v1',generation_mode='RULE')
    run_id=start(client,creds).json()['run_id']
    clock=[100.0]
    worker=Worker(app.state.db,registry,clock=lambda:clock[0])
    for expected in ['QUEUED','QUEUED','FAILED']:
        assert worker.process_once()
        result=client.get(f'/api/agent-runs/{run_id}',headers=auth(creds)).json()
        assert result['status']==expected
        clock[0]+=100
    assert result['attempts']==3 and not worker.process_once()
    retry=start(client,creds,retry_of_run_id=run_id)
    assert retry.status_code==202 and retry.json()['run_id']!=run_id


def test_cancellation_during_provider_call_never_overwrites_cancelled_state(env):
    client,creds,app,registry=env
    entered,release=Event(),Event()
    def slow(snapshot):
        entered.set()
        if not release.wait(5):
            raise RuntimeError('test timeout')
        return {'summary':'must not appear'}
    registry.handlers['REVIEW_SUPPORT']=Handler('REVIEW_SUPPORT',slow,Result,'slow-v1',generation_mode='RULE')
    run_id=start(client,creds).json()['run_id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        running=pool.submit(Worker(app.state.db,registry).process_once)
        assert entered.wait(3)
        try:
            cancelled=client.post(f'/api/agent-runs/{run_id}/cancel',headers=auth(creds),json={'expected_version':1,'reason':'취소'})
            assert cancelled.status_code==200
        finally:
            release.set()
        assert running.result(timeout=3)
    result=client.get(f'/api/agent-runs/{run_id}',headers=auth(creds)).json()
    assert result['status']=='CANCELLED' and result['result'] is None


def test_stale_result_requires_explicit_recomparison(env):
    client,creds,app,registry=env
    run_id=start(client,creds).json()['run_id']
    Worker(app.state.db,registry).process_once()
    client.post('/api/cases/demo-case/tasks',headers=auth(creds),json={'expected_version':1,'type':'FACT_CHECK','assignee_id':'teacher','question':'새 정보'})
    review={'expected_version':2,'decision':'ACCEPT','reason':'변경 대조'}
    response=client.post(f'/api/agent-runs/{run_id}/review',headers=auth(creds),json=review)
    assert response.status_code==409 and response.json()['code']=='STALE_AGENT_RESULT'
    assert client.post(f'/api/agent-runs/{run_id}/review',headers=auth(creds),json={**review,'accept_stale':True}).status_code==200


def test_revoked_access_prevents_external_call_and_foreign_run_read(env):
    client,creds,app,registry=env
    run_id=start(client,creds,'teacher').json()['run_id']
    with app.state.db.transaction() as db:
        db.execute("DELETE FROM case_participants WHERE user_id='teacher'")
    Worker(app.state.db,registry).process_once()
    result=client.get(f'/api/agent-runs/{run_id}',headers=auth(creds)).json()
    assert result['status']=='FAILED' and result['error']['code']=='ACCESS_REVOKED'
    assert client.get(f'/api/agent-runs/{run_id}',headers=auth(creds,'teacher')).status_code==403
    assert client.get(f'/api/agent-runs/{run_id}',headers=auth(creds,'other-admin')).status_code==404
    foreign=client.get(f'/api/agent-runs/{run_id}',headers=auth(creds,'other-admin')).json()
    missing=client.get('/api/agent-runs/missing',headers=auth(creds,'other-admin')).json()
    assert {k:v for k,v in foreign.items() if k!='request_id'}=={k:v for k,v in missing.items() if k!='request_id'}


def test_worker_crash_at_retry_limit_is_terminal(env):
    client,creds,app,registry=env
    run_id=start(client,creds).json()['run_id']
    with app.state.db.transaction() as db:
        db.execute("UPDATE agent_runs SET status='RUNNING',attempts=max_attempts,lease_until=0 WHERE id=?",(run_id,))
    assert not Worker(app.state.db,registry).process_once()
    result=client.get(f'/api/agent-runs/{run_id}',headers=auth(creds)).json()
    assert result['status']=='FAILED' and result['error']['code']=='WORKER_INTERRUPTED'


def test_openai_adapter_payload_refusal_and_invalid_citation():
    snapshot={'sources':[{'ref':{'resource_id':'demo-case'},'data':{'title':'[가상]'}}]}
    calls=[]
    value={'summary':'검토 필요','observations':[{'source_id':'demo-case','kind':'CLAIM','detail':'기록된 주장'}],
           'missing_information':['추가 확인'],'suggested_support':'KEEP_REVIEWING','action_options':['총괄 검토']}
    response=SimpleNamespace(status='completed',output_parsed=value)
    def parse(**kwargs):
        calls.append(kwargs)
        return response
    client=SimpleNamespace(responses=SimpleNamespace(parse=parse))
    adapter=OpenAIAdapter('never-sent-test-key','configured-model',client)
    assert adapter.support_review(snapshot)['summary']=='검토 필요'
    assert calls[0]['store'] is False and calls[0]['text_format'] is SupportReviewResult
    assert 'tools' not in calls[0] and calls[0]['model']=='configured-model'
    response.output_parsed={**value,'observations':[{'source_id':'invented','kind':'FACT','detail':'invalid'}]}
    with pytest.raises(ProviderFailure) as failure:
        adapter.support_review(snapshot)
    assert failure.value.code=='INVALID_CITATION'
    response.output_parsed=None
    with pytest.raises(ProviderFailure):
        adapter.support_review(snapshot)


def test_openai_configuration_does_not_register_a_fake_model(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.delenv('OPENAI_MODEL',raising=False)
    assert create_registry(speech=False).handlers=={}


def test_real_sdk_transport_sends_structured_responses_payload_without_network():
    import httpx2
    import openai
    requests=[]
    value={'summary':'[가상] 검토','observations':[], 'missing_information':['정보 부족'],
           'suggested_support':'KEEP_REVIEWING','action_options':['추가 확인']}
    def transport(request):
        requests.append(request)
        return httpx2.Response(200,json={
            'id':'resp_test','object':'response','created_at':0,'status':'completed',
            'model':'configured-model','error':None,'incomplete_details':None,
            'output':[{'id':'msg_test','type':'message','role':'assistant','status':'completed',
                       'content':[{'type':'output_text','text':json.dumps(value),'annotations':[]}]}],
            'parallel_tool_calls':True,'tool_choice':'auto','tools':[],
        })
    with openai.OpenAI(api_key='test-only-not-a-real-key',http_client=httpx2.Client(transport=httpx2.MockTransport(transport)),max_retries=0) as sdk:
        result=OpenAIAdapter(None,'configured-model',sdk).support_review({'sources':[]})
    assert result['suggested_support']=='KEEP_REVIEWING' and len(requests)==1
    sent=json.loads(requests[0].content)
    assert requests[0].url.path=='/v1/responses' and sent['store'] is False
    assert sent['text']['format']['type']=='json_schema' and sent['text']['format']['strict'] is True


def test_handler_failure_text_is_not_saved(env):
    client,creds,app,registry=env
    def broken(snapshot):
        raise RuntimeError('private complaint and secret API key')
    registry.handlers['REVIEW_SUPPORT']=Handler('REVIEW_SUPPORT',broken,Result,'error-v1',generation_mode='RULE')
    run_id=start(client,creds).json()['run_id']
    Worker(app.state.db,registry).process_once()
    response=client.get(f'/api/agent-runs/{run_id}',headers=auth(creds))
    assert response.json()['status']=='FAILED' and 'private complaint' not in response.text
