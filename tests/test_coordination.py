from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.coordination import resolve_support, utc
from backend.db import Database
from backend.main import create_app
from backend.migration import migrate
from backend.notifications import dispatch_once
from backend.seed import seed


@pytest.fixture
def env(tmp_path):
    path=tmp_path/'coordination.sqlite3'
    credentials=seed(path)
    app=create_app(path,inbox_worker=False)
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','teacher')")
    with TestClient(app,raise_server_exceptions=False) as client:
        yield client,credentials,app.state.db


def headers(creds,user='admin',key=None):
    return {'Authorization':'Bearer '+creds['tokens'][user],'Idempotency-Key':key or str(uuid4())}


def make_task(client,creds):
    response=client.post('/api/cases/demo-case/tasks',headers=headers(creds),json={
        'expected_version':1,'type':'CALLBACK','assignee_id':'teacher','question':'[가상] 일정 확인'})
    assert response.status_code==201
    return response.json()['task_id']


def settings(client,creds,version=1,**changes):
    return client.put('/api/school/settings',headers=headers(creds),json={'expected_settings_version':version,**changes})


def test_task_schedule_permissions_utc_version_and_idempotency(env):
    client,creds,database=env
    task_id=make_task(client,creds)
    path=f'/api/tasks/{task_id}/schedule'
    body={'expected_version':2,'planned_start_at':'2026-11-01T10:00:00+09:00','due_at':'2026-11-01T11:00:00+09:00','reason':'수업 이후 콜백'}
    h=headers(creds,'teacher','schedule-one')
    response=client.put(path,headers=h,json=body)
    assert response.status_code==200 and response.json()['version']==3
    assert response.json()['due_at']=='2026-11-01T02:00:00.000000+00:00'
    assert client.put(path,headers=h,json=body).json()==response.json()
    stale=client.put(path,headers=headers(creds),json=body)
    assert stale.status_code==409 and stale.json()['code']=='VERSION_CONFLICT'
    with database.transaction() as db:
        assert db.execute('SELECT owner_id FROM cases').fetchone()[0]=='admin'
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','outsider')")
    assert client.put(path,headers=headers(creds,'outsider'),json={**body,'expected_version':3}).status_code==403
    assert client.put(path,headers=headers(creds),json={**body,'expected_version':3,'due_at':'2026-11-01T11:00:00'}).status_code==422
    assert client.put(path,headers=headers(creds),json={**body,'expected_version':3,'due_at':'2026-10-01T00:00:00Z'}).status_code==422
    record=client.get('/api/cases/demo-case',headers=headers(creds)).json()
    assert record['tasks'][0]['schedule']['due_at']==response.json()['due_at']


def test_absence_routes_support_and_keeps_case_owner(env):
    client,creds,database=env
    assert settings(client,creds,duty_admin_id='deputy').status_code==200
    at=datetime.now(timezone.utc)
    absence=client.post('/api/school/absences',headers=headers(creds),json={
        'expected_settings_version':2,'user_id':'admin','substitute_id':'deputy',
        'starts_at':utc(at-timedelta(hours=1)),'ends_at':utc(at+timedelta(hours=1))})
    assert absence.status_code==201
    support=client.post('/api/cases/demo-case/support-requests',headers=headers(creds,'teacher'),json={
        'expected_version':1,'coordinator_id':'admin','type':'URGENT','reason':'[가상] 긴급 지원'})
    assert support.status_code==201 and support.json()['coordinator_id']=='deputy'
    support_id=support.json()['support_request_id']
    assert client.patch(f'/api/support-requests/{support_id}',headers=headers(creds),json={'expected_version':2,'status':'ACKNOWLEDGED'}).status_code==403
    assert client.patch(f'/api/support-requests/{support_id}',headers=headers(creds,'deputy'),json={'expected_version':2,'status':'ACKNOWLEDGED'}).status_code==200
    record=client.get('/api/cases/demo-case',headers=headers(creds)).json()
    assert record['owner_id']=='admin' and record['support_requests'][0]['requested_coordinator_id']=='admin'
    with database.transaction() as db:
        assert resolve_support(db,'demo-school','admin',utc(at+timedelta(hours=1)))[0]=='admin'


def test_school_settings_are_versioned_scoped_and_absence_overlap_is_rejected(env):
    client,creds,database=env
    assert settings(client,creds,duty_admin_id='other-admin').status_code==422
    assert settings(client,creds,duty_admin_id='deputy').json()['settings_version']==2
    assert settings(client,creds).json()['code']=='SETTINGS_VERSION_CONFLICT'
    assert client.get('/api/school/settings',headers=headers(creds,'teacher')).status_code==403
    body={'expected_settings_version':2,'user_id':'admin','substitute_id':'deputy',
          'starts_at':'2026-11-01T00:00:00Z','ends_at':'2026-11-02T00:00:00Z'}
    h=headers(creds,key='absence-replay')
    first=client.post('/api/school/absences',headers=h,json=body)
    assert first.status_code==201 and client.post('/api/school/absences',headers=h,json=body).json()==first.json()
    assert client.post('/api/school/absences',headers=headers(creds),json={**body,'expected_settings_version':3}).json()['code']=='ABSENCE_OVERLAP'
    assert client.post('/api/school/absences',headers=headers(creds),json={**body,'expected_settings_version':3,'substitute_id':'teacher'}).status_code==422
    with database.transaction() as db:
        assert db.execute('SELECT version FROM school_settings').fetchone()[0]==3
        assert db.execute('SELECT count(*) FROM school_audit_events').fetchone()[0]==2
        assert db.execute('SELECT version FROM cases').fetchone()[0]==1


def test_outbox_delivery_and_user_receipt_do_not_acknowledge_support_or_change_case_version(env):
    client,creds,database=env
    task_id=make_task(client,creds)
    assert client.get('/api/notifications',headers=headers(creds,'teacher')).json()==[]
    assert dispatch_once(database)==1
    inbox=client.get('/api/notifications',headers=headers(creds,'teacher')).json()
    assert len(inbox)==1 and inbox[0]['status']=='DELIVERED'
    notification_id=inbox[0]['id']
    assert client.post(f'/api/notifications/{notification_id}/acknowledge',headers=headers(creds),json={}).status_code==404
    h=headers(creds,'teacher','read-one')
    first=client.post(f'/api/notifications/{notification_id}/acknowledge',headers=h,json={})
    repeated=client.post(f'/api/notifications/{notification_id}/acknowledge',headers=h,json={})
    assert first.status_code==200 and repeated.json()==first.json()
    with database.transaction() as db:
        assert db.execute('SELECT count(*) FROM notification_events').fetchone()[0]==3
        assert db.execute('SELECT version FROM cases').fetchone()[0]==2
        assert db.execute('SELECT status FROM tasks WHERE id=?',(task_id,)).fetchone()[0]=='REQUESTED'


def test_failed_delivery_is_bounded_retriable_and_access_revocation_hides_inbox(env):
    client,creds,database=env
    make_task(client,creds)
    with database.transaction() as db:
        db.execute("UPDATE memberships SET active=0 WHERE user_id='teacher'")
    at=datetime.now(timezone.utc)+timedelta(seconds=5)
    for seconds in [0,10,20]:
        dispatch_once(database,utc(at+timedelta(seconds=seconds)))
    status=client.get('/api/school/notification-status',headers=headers(creds)).json()[0]
    assert status['status']=='FAILED' and status['attempts']==3
    with database.transaction() as db:
        db.execute("UPDATE memberships SET active=1 WHERE user_id='teacher'")
    assert client.post(f'/api/notifications/{status["id"]}/retry',headers=headers(creds),json={}).status_code==200
    dispatch_once(database,utc(at+timedelta(seconds=30)))
    assert len(client.get('/api/notifications',headers=headers(creds,'teacher')).json())==1
    with database.transaction() as db:
        db.execute("DELETE FROM case_participants WHERE user_id='teacher'")
    assert client.get('/api/notifications',headers=headers(creds,'teacher')).json()==[]
    assert client.post(f'/api/notifications/{status["id"]}/acknowledge',headers=headers(creds,'teacher'),json={}).status_code==403


def test_dispatchers_do_not_duplicate_delivery(env):
    client,creds,database=env
    make_task(client,creds)
    with ThreadPoolExecutor(max_workers=2) as pool:
        counts=list(pool.map(lambda _:dispatch_once(database),range(2)))
    assert sorted(counts)==[0,1]
    with database.transaction() as db:
        assert db.execute("SELECT count(*) FROM notification_events WHERE status='DELIVERED'").fetchone()[0]==1


def test_overdue_notifications_are_deduped_and_stop_after_completion(env):
    client,creds,database=env
    task_id=make_task(client,creds)
    at=datetime.now(timezone.utc)
    changed=client.put(f'/api/tasks/{task_id}/schedule',headers=headers(creds),json={
        'expected_version':2,'due_at':utc(at-timedelta(minutes=1)),'reason':'[가상] 지연 확인'})
    assert changed.status_code==200
    dispatch_once(database,utc(at))
    dispatch_once(database,utc(at))
    with database.transaction() as db:
        assert db.execute("SELECT count(*) FROM inbox_notifications WHERE kind='TASK_OVERDUE'").fetchone()[0]==2
    assert client.patch(f'/api/tasks/{task_id}',headers=headers(creds,'teacher'),json={'expected_version':3,'status':'COMPLETED','reply':'확인 완료'}).status_code==200
    dispatch_once(database,utc(at+timedelta(days=1)))
    with database.transaction() as db:
        assert db.execute("SELECT count(*) FROM inbox_notifications WHERE kind='TASK_OVERDUE'").fetchone()[0]==2


def test_unconfirmed_support_reroutes_once_per_assignment_timeout(env):
    client,creds,database=env
    assert settings(client,creds,duty_admin_id='deputy',support_ack_minutes=1).status_code==200
    response=client.post('/api/cases/demo-case/support-requests',headers=headers(creds,'teacher'),json={
        'expected_version':1,'coordinator_id':'admin','type':'ATTEND','reason':'[가상] 동석 요청'})
    assert response.json()['coordinator_id']=='admin'
    support_id=response.json()['support_request_id']
    at=datetime.now(timezone.utc)+timedelta(minutes=2)
    dispatch_once(database,utc(at))
    dispatch_once(database,utc(at))
    record=client.get('/api/cases/demo-case',headers=headers(creds)).json()
    assert record['version']==3 and record['owner_id']=='admin'
    assert record['support_requests'][0]['coordinator_id']=='deputy'
    assert record['support_requests'][0]['requested_coordinator_id']=='admin'
    assert client.patch(f'/api/support-requests/{support_id}',headers=headers(creds,'deputy'),json={'expected_version':3,'status':'ACKNOWLEDGED'}).status_code==200
    dispatch_once(database,utc(at+timedelta(minutes=2)))
    with database.transaction() as db:
        assert db.execute("SELECT count(*) FROM audit_events WHERE action='SUPPORT_REROUTED'").fetchone()[0]==1


def test_absence_cycles_preserve_urgent_request_and_do_not_disable_urgent_alerts(env):
    client,creds,database=env
    assert settings(client,creds,alerts_enabled=False).status_code==200
    at=datetime.now(timezone.utc)
    for version,user,substitute in [(2,'admin','deputy'),(3,'deputy','admin')]:
        assert client.post('/api/school/absences',headers=headers(creds),json={
            'expected_settings_version':version,'user_id':user,'substitute_id':substitute,
            'starts_at':utc(at-timedelta(hours=1)),'ends_at':utc(at+timedelta(hours=1))}).status_code==201
    response=client.post('/api/cases/demo-case/support-requests',headers=headers(creds,'teacher'),json={
        'expected_version':1,'coordinator_id':'admin','type':'URGENT','reason':'[가상] 부재 중 도움'})
    assert response.status_code==201 and response.json()['routing_reason']=='NO_AVAILABLE_SUBSTITUTE'
    assert dispatch_once(database)==3
    with database.transaction() as db:
        assert db.execute('SELECT owner_id FROM cases').fetchone()[0]=='admin'
        assert db.execute("SELECT COUNT(*) FROM inbox_notifications WHERE severity!='URGENT'").fetchone()[0]==0


def test_handover_decline_cancel_keep_owner_and_allow_new_request_and_closure(env):
    client,creds,database=env
    def create(version):
        return client.post('/api/cases/demo-case/handovers',headers=headers(creds),json={'expected_version':version,'to_owner_id':'deputy','reason':'[가상] 인계'})
    handover_id=create(1).json()['handover_id']
    assert client.post(f'/api/handovers/{handover_id}/decline',headers=headers(creds),json={'expected_version':2,'reason':'잘못된 행위자'}).status_code==403
    declined=client.post(f'/api/handovers/{handover_id}/decline',headers=headers(creds,'deputy'),json={'expected_version':2,'reason':'부재로 인수 불가'})
    assert declined.json()['owner_id']=='admin' and declined.json()['status']=='DECLINED'
    second=create(3).json()['handover_id']
    assert client.post(f'/api/handovers/{second}/cancel',headers=headers(creds),json={'expected_version':4,'reason':'학교 내 협의 변경'}).json()['status']=='CANCELLED'
    closed=client.post('/api/cases/demo-case/close',headers=headers(creds),json={'expected_version':5,'reason':'B 범위 종결 가드 확인'})
    assert closed.status_code==200
    with database.transaction() as db:
        assert db.execute('SELECT owner_id FROM cases').fetchone()[0]=='admin'


def test_outbox_rolls_back_with_domain_audit_failure(env):
    client,creds,database=env
    with database.transaction() as db:
        db.execute("CREATE TRIGGER deny_audit BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT,'fail'); END")
    response=client.post('/api/cases/demo-case/tasks',headers=headers(creds),json={
        'expected_version':1,'type':'FACT_CHECK','assignee_id':'teacher','question':'확인'})
    assert response.status_code==500
    with database.transaction() as db:
        assert db.execute('SELECT count(*) FROM inbox_notifications').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM notification_events').fetchone()[0]==0


def test_upgrade_preserves_pending_handover_and_support_metadata(tmp_path):
    directory=tmp_path/'legacy-migrations'
    directory.mkdir()
    files=sorted(Path('backend/migrations').glob('*.sql'))
    for file in files:
        if file.name<'20261030_000004_B_coordination.sql':
            shutil.copyfile(file,directory/file.name)
    path=tmp_path/'upgrade.sqlite3'
    migrate(path,directory)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO memberships VALUES ('admin','school','ADMIN',1)")
        db.execute("INSERT INTO cases VALUES ('case','school','old','admin','OPEN',4)")
        db.execute("INSERT INTO handovers VALUES ('handover','case','admin','other','reason','PENDING','2026-10-30T00:00:00+00:00')")
        db.execute("INSERT INTO support_requests VALUES ('support','case','admin','admin','ATTEND','reason','REQUESTED',NULL,'2026-10-30T00:00:00+00:00')")
    database=Database(path)
    with database.transaction() as db:
        assert db.execute('SELECT id,status FROM handovers').fetchone()[:]==('handover','PENDING')
        support=db.execute('SELECT * FROM support_requests').fetchone()
        assert support['requested_coordinator_id']=='admin' and support['assigned_at']==support['created_at']
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_approved_permission_changes_are_scoped_revoke_sessions_and_replay_safely(env):
    client,creds,database=env
    body={'expected_settings_version':1,'role':'ADMIN','active':True,'reason':'[가상] 학교 지원 관리자 지정'}
    assert client.put('/api/school/members/outsider',headers=headers(creds,'teacher'),json=body).status_code==403
    assert client.put('/api/school/members/other-admin',headers=headers(creds),json=body).status_code==404
    assert client.put('/api/school/members/admin',headers=headers(creds),json=body).status_code==403
    h=headers(creds,key='promote-fictional')
    first=client.put('/api/school/members/outsider',headers=h,json=body)
    assert first.status_code==200 and first.json()['sessions_revoked'] is True
    assert client.put('/api/school/members/outsider',headers=h,json=body).json()==first.json()
    assert client.get('/api/session',headers=headers(creds,'outsider')).status_code==401
    with database.transaction() as db:
        assert db.execute("SELECT role FROM memberships WHERE user_id='outsider'").fetchone()[0]=='ADMIN'
        assert db.execute("SELECT COUNT(*) FROM school_audit_events WHERE action='MEMBER_PERMISSION_CHANGED'").fetchone()[0]==1


def test_reactivation_never_restores_revoked_tokens(env):
    client,creds,database=env
    body={'expected_settings_version':1,'role':'TEACHER','active':False,'reason':'[가상] 계정 중지'}
    assert client.put('/api/school/members/outsider',headers=headers(creds),json=body).status_code==200
    assert client.put('/api/school/members/outsider',headers=headers(creds),json={**body,'expected_settings_version':2,'active':True,'reason':'[가상] 재활성'}).status_code==200
    assert client.get('/api/session',headers=headers(creds,'outsider')).status_code==401
    from backend.db import issue_session
    with database.transaction() as db:
        new_token=issue_session(db,'outsider','demo-school')
    assert client.get('/api/session',headers={'Authorization':'Bearer '+new_token}).status_code==200


def test_permission_change_blocks_remaining_case_task_and_duty_responsibility(env):
    client,creds,database=env
    body={'expected_settings_version':1,'role':'TEACHER','active':False,'reason':'[가상] 책임 유지 검사'}
    owner=client.put('/api/school/members/admin',headers=headers(creds,'deputy'),json=body)
    assert owner.status_code==409 and owner.json()['pending']['owners']==1
    make_task(client,creds)
    task=client.put('/api/school/members/teacher',headers=headers(creds),json=body)
    assert task.status_code==409 and task.json()['pending']['tasks']==1
    assert settings(client,creds,duty_admin_id='deputy').status_code==200
    duty=client.put('/api/school/members/deputy',headers=headers(creds),json={**body,'expected_settings_version':2})
    assert duty.status_code==409 and duty.json()['pending']['duty']==1
    with database.transaction() as db:
        assert db.execute("SELECT active FROM memberships WHERE user_id='teacher'").fetchone()[0]==1


def test_permission_update_and_session_revocation_roll_back_if_school_audit_fails(env):
    client,creds,database=env
    with database.transaction() as db:
        db.execute("CREATE TRIGGER deny_school_audit BEFORE INSERT ON school_audit_events BEGIN SELECT RAISE(ABORT,'fail'); END")
    response=client.put('/api/school/members/outsider',headers=headers(creds),json={
        'expected_settings_version':1,'role':'ADMIN','active':True,'reason':'[가상] 감사 실패'})
    assert response.status_code==500
    session=client.get('/api/session',headers=headers(creds,'outsider'))
    assert session.status_code==200 and session.json()['role']=='TEACHER'
    with database.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM idempotency').fetchone()[0]==0


def test_reassignment_keeps_owner_and_history_and_releases_old_assignee_responsibility(env):
    client,creds,database=env
    task_id=make_task(client,creds)
    assert client.patch(f'/api/tasks/{task_id}',headers=headers(creds,'teacher'),json={'expected_version':2,'status':'ACKNOWLEDGED','reply':'[가상] 이전 수행자 확인'}).status_code==200
    changed=client.post(f'/api/tasks/{task_id}/reassign',headers=headers(creds),json={'expected_version':3,'assignee_id':'outsider','reason':'[가상] 부재 대체'})
    assert changed.status_code==200 and changed.json()['owner_id']=='admin' and changed.json()['status']=='REQUESTED'
    assert client.patch(f'/api/tasks/{task_id}',headers=headers(creds,'teacher'),json={'expected_version':4,'status':'COMPLETED','reply':'이전 수행자 회신'}).status_code==403
    # Task reassignment alone must not release the remaining homeroom duty.
    blocked=client.put('/api/school/members/teacher',headers=headers(creds),json={'expected_settings_version':1,'role':'TEACHER','active':False,'reason':'[가상] 인계 후 중지'})
    assert blocked.status_code==409
    removed=client.post('/api/school/responsibilities/resp-home/remove',headers=headers(creds),json={'expected_settings_version':1,'reason':'[가상] 담임 업무분장 해제'})
    assert removed.status_code==200
    assert client.put('/api/school/members/teacher',headers=headers(creds),json={'expected_settings_version':2,'role':'TEACHER','active':False,'reason':'[가상] 모든 책임 인계 후 중지'}).status_code==200
    assert client.patch(f'/api/tasks/{task_id}',headers=headers(creds,'outsider'),json={'expected_version':4,'status':'COMPLETED','reply':'새 수행자 회신'}).status_code==200
    history=client.get('/api/cases/demo-case/timeline',headers=headers(creds)).json()
    assert any(event['payload'].get('reply')=='[가상] 이전 수행자 확인' for event in history)
    assert any(event['action']=='TASK_REASSIGNED' for event in history)


def test_old_unread_notification_is_not_hidden_by_new_acknowledged_history(env):
    from backend.notifications import enqueue
    client,creds,database=env
    task_id=make_task(client,creds)
    with database.transaction() as db:
        oldest=db.execute('SELECT id FROM inbox_notifications').fetchone()[0]
        for index in range(105):
            enqueue(db,'demo-case','teacher','TASK_CREATED',task_id,f'fixture:{index}')
        db.execute("UPDATE inbox_notifications SET status='ACKNOWLEDGED'")
        db.execute("UPDATE inbox_notifications SET status='DELIVERED' WHERE id=?",(oldest,))
    inbox=client.get('/api/notifications',headers=headers(creds,'teacher')).json()
    assert len(inbox)==100 and inbox[0]['id']==oldest and inbox[0]['status']=='DELIVERED'


def test_new_absence_reroutes_existing_request_without_waiting_for_ack_timeout(env):
    client,creds,database=env
    assert settings(client,creds,duty_admin_id='deputy',support_ack_minutes=10080).status_code==200
    response=client.post('/api/cases/demo-case/support-requests',headers=headers(creds,'teacher'),json={
        'expected_version':1,'coordinator_id':'admin','type':'URGENT','reason':'[가상] 시작 전 요청'})
    assert response.json()['coordinator_id']=='admin'
    at=datetime.now(timezone.utc)
    assert client.post('/api/school/absences',headers=headers(creds),json={
        'expected_settings_version':2,'user_id':'admin','substitute_id':'deputy',
        'starts_at':utc(at-timedelta(minutes=1)),'ends_at':utc(at+timedelta(hours=1))}).status_code==201
    dispatch_once(database)
    with database.transaction() as db:
        support=db.execute('SELECT coordinator_id,routing_reason FROM support_requests').fetchone()
        assert support['coordinator_id']=='deputy' and support['routing_reason']=='ABSENCE_SUBSTITUTE'
        assert db.execute('SELECT owner_id FROM cases').fetchone()[0]=='admin'


def test_urgent_delivery_is_prioritized_over_normal_backlog(env):
    from backend.notifications import enqueue
    client,creds,database=env
    task_id=make_task(client,creds)
    with database.transaction() as db:
        for index in range(105):
            enqueue(db,'demo-case','teacher','TASK_CREATED',task_id,f'backlog:{index}')
        urgent=enqueue(db,'demo-case','admin','SUPPORT_REQUESTED','fictional-support','urgent-priority',severity='URGENT')
    assert dispatch_once(database)==100
    with database.transaction() as db:
        assert db.execute('SELECT status FROM inbox_notifications WHERE id=?',(urgent,)).fetchone()[0]=='DELIVERED'
        assert db.execute("SELECT COUNT(*) FROM inbox_notifications WHERE severity='NORMAL' AND status='QUEUED'").fetchone()[0]>0
