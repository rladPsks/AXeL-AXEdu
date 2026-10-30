import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.agents import Handler, Registry
from backend.main import create_app
from backend.seed import seed
from backend.worker import Worker


@pytest.fixture
def env(tmp_path):
    path=tmp_path/'comparison.sqlite3'
    creds=seed(path)
    registry=Registry()
    class Result(BaseModel):
        summary:str
    registry.register(Handler('REVIEW_SUPPORT',lambda snapshot:{'summary':'[가상] 버전 대조'},Result,'comparison-test',generation_mode='RULE'))
    app=create_app(path,agent_registry=registry,inbox_worker=False)
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO cases(id,school_id,title,owner_id,status,version) VALUES ('previous','demo-school','[가상] 이전 문의','deputy','OPEN',1)")
        db.execute("INSERT INTO cases(id,school_id,title,owner_id,status,version) VALUES ('foreign','other-school','[가상] 다른 학교','other-admin','OPEN',1)")
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','teacher')")
    with TestClient(app,raise_server_exceptions=False) as client:
        yield client,creds,app,registry


def auth(creds,user='admin',key=None):
    return {'Authorization':'Bearer '+creds['tokens'][user],'Idempotency-Key':key or str(uuid4())}


def document(version=1,**extra):
    return {'expected_version':version,'kind':'INTAKE','label':'[가상] 접수 원문','content':'[가상] 답변을 받지 못했다는 재문의',
            'provenance':'담당자가 수동 입력한 가상 자료','occurred_at':'2026-10-01T10:00:00+09:00',**extra}


def add_document(client,creds,case='demo-case',payload=None):
    return client.post(f'/api/cases/{case}/documents',headers=auth(creds),json=payload or document())


def test_document_versions_are_immutable_and_preserve_previous_content(env):
    client,creds,app,_=env
    first=add_document(client,creds)
    assert first.status_code==201
    doc=first.json()['document_id']
    original=first.json()['document_version_id']
    body={'expected_version':2,'expected_document_revision':1,'content':'[가상] 이전 답변이 있었으나 새 증거를 제시함',
          'provenance':'가상 정정 확인','occurred_at':'2026-10-02T10:00:00+09:00'}
    headers=auth(creds,key='append')
    second=client.post(f'/api/documents/{doc}/versions',headers=headers,json=body)
    assert second.status_code==201 and second.json()['document_revision']==2
    assert client.post(f'/api/documents/{doc}/versions',headers=headers,json=body).json()==second.json()
    assert client.get('/api/document-versions/'+original,headers=auth(creds)).json()['content']==document()['content']
    versions=client.get('/api/cases/demo-case/documents',headers=auth(creds)).json()
    assert [item['revision'] for item in versions]==[1,2]
    assert versions[0]['occurred_at']=='2026-10-01T01:00:00.000000+00:00'
    conflict=client.post(f'/api/documents/{doc}/versions',headers=auth(creds),json={**body,'expected_version':3})
    assert conflict.json()['code']=='DOCUMENT_VERSION_CONFLICT'
    with app.state.db.transaction() as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE case_document_versions SET content='원문 변경 시도'")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('DELETE FROM case_documents')


def test_document_role_school_file_delivery_and_audit_boundaries(env,monkeypatch):
    client,creds,app,_=env
    assert client.post('/api/cases/demo-case/documents',headers=auth(creds,'teacher'),json=document()).status_code==403
    assert add_document(client,creds,payload=document(delivery_state='DELIVERED')).json()['code']=='INVALID_DELIVERY_STATE'
    assert add_document(client,creds,payload=document(occurred_at='2026-10-01T10:00:00')).status_code==422
    assert client.get('/api/cases/foreign/documents',headers=auth(creds)).status_code==404
    first=add_document(client,creds).json()
    assert client.get('/api/document-versions/'+first['document_version_id'],headers=auth(creds,'other-admin')).status_code==404
    assert client.get('/api/document-versions/'+first['document_version_id'],headers=auth(creds,'teacher')).status_code==403
    assert 'CASE_DOCUMENT_RECORDED' not in client.get('/api/cases/demo-case/timeline',headers=auth(creds,'teacher')).text
    def broken(*args,**kwargs):
        raise RuntimeError('audit failed')
    with monkeypatch.context() as patch:
        patch.setattr('backend.commands.audit',broken)
        assert add_document(client,creds,payload=document(2)).status_code==500
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM case_documents').fetchone()[0]==1
        assert db.execute("SELECT version FROM cases WHERE id='demo-case'").fetchone()[0]==2


def profile(client,creds,case,version=1,**extra):
    return client.put(f'/api/cases/{case}/comparison-profile',headers=auth(creds),json={
        'expected_version':version,'person_key':'local-person-1','issue_key':'local-issue-1','received_at':'2026-10-30T10:00:00+09:00',**extra})


def test_school_policy_is_unset_then_window_and_threshold_use_cases_not_versions(env):
    client,creds,app,_=env
    assert profile(client,creds,'demo-case').status_code==200
    assert profile(client,creds,'previous',received_at='2026-10-01T10:00:00+09:00').status_code==200
    initial=client.get('/api/cases/demo-case/comparison',headers=auth(creds)).json()
    assert not initial['policy']['configured'] and initial['review_threshold_met'] is None
    assert initial['candidate_count']==1 and initial['candidates'][0]['matches']==['SAME_PERSON','SAME_ISSUE']
    assert client.put('/api/school/repeat-settings',headers=auth(creds),json={'expected_settings_version':1,'window_days':10,'minimum_count':2}).status_code==200
    assert client.get('/api/cases/demo-case/comparison',headers=auth(creds)).json()['candidate_count']==0
    assert client.put('/api/school/repeat-settings',headers=auth(creds),json={'expected_settings_version':2,'window_days':40,'minimum_count':2,'response_delay_hours':24}).status_code==200
    result=client.get('/api/cases/demo-case/comparison',headers=auth(creds)).json()
    assert result['review_threshold_met'] and result['count_including_current']==2
    assert client.get('/api/cases/demo-case/comparison',headers=auth(creds,'teacher')).status_code==403
    assert client.get('/api/school/repeat-settings',headers=auth(creds,'other-admin')).json()['configured'] is False
    assert 'local-person-1' not in client.get('/api/cases/demo-case/timeline',headers=auth(creds,'teacher')).text
    assert profile(client,creds,'previous',2,received_at='2026-11-01T00:00:00Z').status_code==200
    assert client.get('/api/cases/demo-case/comparison',headers=auth(creds)).json()['candidate_count']==0


def test_relation_versions_both_cases_are_atomic_and_reversible_without_owner_or_participation_changes(env,monkeypatch):
    client,creds,app,_=env
    path='/api/cases/demo-case/relations'
    body={'expected_version':1,'related_case_id':'previous','expected_related_version':1,'state':'LINKED','basis':'BOTH','reason':'[가상] 원문 대조 후 연결'}
    headers=auth(creds,key='relation')
    def broken(*args,**kwargs):
        raise RuntimeError('audit failed')
    with monkeypatch.context() as patch:
        patch.setattr('backend.commands.audit',broken)
        assert client.post(path,headers=headers,json=body).status_code==500
    with app.state.db.transaction() as db:
        assert db.execute('SELECT count(*) FROM case_relation_events').fetchone()[0]==0
        assert [row[0] for row in db.execute("SELECT version FROM cases WHERE school_id='demo-school'")]==[1,1]
    first=client.post(path,headers=headers,json=body)
    assert first.status_code==201 and first.json()['version']==2 and first.json()['related_case_version']==2
    assert client.post(path,headers=headers,json=body).json()==first.json()
    separated=client.post('/api/cases/previous/relations',headers=auth(creds),json={**body,'expected_version':2,'related_case_id':'demo-case','expected_related_version':2,'previous_relation_id':first.json()['relation_id'],'state':'SEPARATED','reason':'[가상] 별도 새 사실로 분리'})
    assert separated.status_code==201
    pair=client.get('/api/cases/demo-case/compare/previous',headers=auth(creds)).json()
    assert [item['state'] for item in pair['relation_history']]==['SEPARATED','LINKED']
    assert pair['current']['case']['owner_id']=='admin' and pair['related']['case']['owner_id']=='deputy'
    with app.state.db.transaction() as db:
        assert db.execute("SELECT 1 FROM case_participants WHERE case_id='previous' AND user_id='teacher'").fetchone() is None
    assert client.get('/api/cases/previous',headers=auth(creds,'teacher')).status_code==403
    assert client.post(path,headers=auth(creds),json={**body,'expected_version':3,'expected_related_version':2}).json()['code']=='RELATED_VERSION_CONFLICT'
    assert client.post(path,headers=auth(creds),json={**body,'expected_version':3,'related_case_id':'foreign'}).status_code==404
    assert 'CASE_COMPARISON_RELATION_CHANGED' not in client.get('/api/cases/demo-case/timeline',headers=auth(creds,'teacher')).text


def test_response_review_uses_latest_correction_and_never_claims_actual_nonresponse(env):
    client,creds,app,_=env
    assert add_document(client,creds).status_code==201
    reply=add_document(client,creds,payload=document(2,kind='RESPONSE',delivery_state='DELIVERED',occurred_at='2026-10-02T10:00:00Z')).json()
    assert client.put('/api/school/repeat-settings',headers=auth(creds),json={'expected_settings_version':1,'window_days':30,'minimum_count':3,'response_delay_hours':24}).status_code==200
    read=lambda:client.get('/api/cases/demo-case/compare/previous',headers=auth(creds)).json()['current']['response_review']
    assert read()['delivered_response_recorded'] and not read()['review_due_from_records']
    corrected={'expected_version':3,'expected_document_revision':1,'content':'[가상] 발송 실패 확인','provenance':'가상 오류 정정','occurred_at':'2026-10-02T10:00:00Z','delivery_state':'NOT_DELIVERED'}
    assert client.post(f"/api/documents/{reply['document_id']}/versions",headers=auth(creds),json=corrected).status_code==201
    assert read()['review_due_from_records'] and not read()['delivered_response_recorded']
    assert '실제 미응답' in read()['notice']


def test_versioned_sources_are_usable_for_ai_and_human_decisions_but_not_by_teachers(env):
    client,creds,app,registry=env
    first=add_document(client,creds).json()
    ref={'resource_type':'DOCUMENT_VERSION','resource_id':first['document_version_id'],'version':1}
    start=lambda user='admin',**extra:client.post('/api/cases/demo-case/agent-runs',headers=auth(creds,user),json={'expected_version':2,'purpose':'REVIEW_SUPPORT','input_refs':[ref],**extra})
    assert start('teacher').status_code==403
    assert start(input_refs=[{**ref,'version':2}]).json()['code']=='INPUT_VERSION_CONFLICT'
    run=start().json()['run_id']
    assert Worker(app.state.db,registry).process_once()
    with app.state.db.transaction() as db:
        snapshot=json.loads(db.execute('SELECT snapshot FROM agent_runs WHERE id=?',(run,)).fetchone()[0])
        assert snapshot['sources'][0]['data']['content']==document()['content']
    decision={'expected_version':2,'decision_type':'KEEP_REVIEWING','reason':'추가 사실 대조','target':'학교 대응팀','route':'공동 검토','remaining_school_work':'이전 답변 확인',
              'input_refs':[ref],'observations':[{'source_id':ref['resource_id'],'kind':'CLAIM','detail':'답변을 못 받았다는 주장'}]}
    result=client.post('/api/cases/demo-case/support-decisions',headers=auth(creds),json=decision)
    assert result.status_code==201
    saved=client.get('/api/support-decisions/'+result.json()['decision_id'],headers=auth(creds)).json()['snapshot']
    assert saved['sources'][0]['data']['revision']==1


def test_document_file_links_are_same_case_and_worker_rechecks_role(env):
    client,creds,app,registry=env
    upload=lambda case,version:client.post(f'/api/cases/{case}/files?filename=evidence.txt&expected_version={version}&visibility=RESTRICTED',headers={**auth(creds),'Content-Type':'application/octet-stream'},content='[가상] 원문 첨부'.encode())
    file=upload('demo-case',1).json()['file_id']
    other=upload('previous',1).json()['file_id']
    assert add_document(client,creds,payload=document(2,file_id=other)).json()['code']=='DOCUMENT_FILE_CASE_MISMATCH'
    recorded=add_document(client,creds,payload=document(2,file_id=file)).json()
    with app.state.db.transaction() as db:
        assert db.execute('SELECT file_id FROM case_document_versions WHERE id=?',(recorded['document_version_id'],)).fetchone()[0]==file
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','admin')")
    queued=client.post('/api/cases/demo-case/agent-runs',headers=auth(creds),json={'expected_version':3,'purpose':'REVIEW_SUPPORT','input_refs':[{'resource_type':'DOCUMENT_VERSION','resource_id':recorded['document_version_id'],'version':1}]}).json()['run_id']
    with app.state.db.transaction() as db:
        db.execute("UPDATE memberships SET role='TEACHER' WHERE user_id='admin' AND school_id='demo-school'")
    assert Worker(app.state.db,registry).process_once()
    with app.state.db.transaction() as db:
        run=db.execute('SELECT status,result,error FROM agent_runs WHERE id=?',(queued,)).fetchone()
        assert run['status']=='FAILED' and run['result'] is None and json.loads(run['error'])['code']=='ACCESS_REVOKED'


def test_completed_document_generation_is_hidden_from_list_after_role_change(env):
    client,creds,app,registry=env
    version=add_document(client,creds).json()['document_version_id']
    queued=client.post('/api/cases/demo-case/agent-runs',headers=auth(creds),json={'expected_version':2,'purpose':'REVIEW_SUPPORT','input_refs':[{'resource_type':'DOCUMENT_VERSION','resource_id':version,'version':1}]}).json()['run_id']
    assert Worker(app.state.db,registry).process_once()
    assert len(client.get('/api/cases/demo-case/agent-runs',headers=auth(creds)).json())==1
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','admin')")
        db.execute("UPDATE memberships SET role='TEACHER' WHERE user_id='admin' AND school_id='demo-school'")
    assert client.get('/api/agent-runs/'+queued,headers=auth(creds)).status_code==403
    assert client.get('/api/cases/demo-case/agent-runs',headers=auth(creds)).json()==[]
