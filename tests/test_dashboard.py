import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.agents import Registry
from backend.db import now, uid
from backend.main import create_app
from backend.seed import seed


def auth(creds, user='admin'):
    return {'Authorization': 'Bearer ' + creds['tokens'][user], 'Idempotency-Key': str(uuid4())}


def log(client, creds, user='admin', **extra):
    body = {'expected_version': 1, 'staff_id': 'teacher', 'kind': 'CALLBACK',
            'occurred_at': '2026-10-30T10:00:00+09:00', **extra}
    return client.post('/api/cases/demo-case/activities', headers=auth(creds, user), json=body)


@pytest.fixture
def env(tmp_path):
    path = tmp_path / 'dashboard.sqlite3'
    creds = seed(path)
    app = create_app(path, agent_registry=Registry())
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO case_participants(case_id,user_id) VALUES ('demo-case','teacher')")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, creds, app, path


def insert_activity(path, school, case, staff, occurred_at, duration=None, kind='CALLBACK'):
    db = sqlite3.connect(path)
    db.execute('INSERT INTO activity_logs(id,case_id,school_id,staff_id,recorded_by,kind,occurred_at,duration_seconds,created_at) '
               'VALUES (?,?,?,?,?,?,?,?,?)', (uid(), case, school, staff, staff, kind, occurred_at, duration, now()))
    db.commit()
    db.close()


def dashboard(client, creds, user='admin', **params):
    return client.get('/api/dashboard', headers={'Authorization': 'Bearer ' + creds['tokens'][user]}, params=params)


def test_dashboard_is_administrator_only(env):
    client, creds, *_ = env
    assert dashboard(client, creds, 'teacher').status_code == 403
    assert client.get('/api/dashboard').status_code == 401


def test_missing_duration_is_never_counted_as_zero_and_staff_are_not_ranked(env):
    client, creds, *_ = env
    assert log(client, creds, duration_seconds=600).status_code == 201
    assert log(client, creds).json()['duration_recorded'] is False
    assert log(client, creds, staff_id='admin', kind='SUPPORT_ACTION', duration_seconds=60).status_code == 201
    result = dashboard(client, creds, **{'from': '2026-10-30', 'to': '2026-10-30'}).json()
    rows = {row['staff_id']: row for row in result['staff_activity']}
    assert rows['teacher']['recorded_seconds'] == 600
    assert rows['teacher']['entries'] == 2 and rows['teacher']['entries_without_duration'] == 1
    assert rows['teacher']['by_kind'] == {'CALLBACK': 2}
    # Alphabetical, even though the teacher recorded more time.
    assert [row['staff_id'] for row in result['staff_activity']] == ['admin', 'teacher']
    assert not {'rank', 'score', 'ranking'} & set(rows['teacher'])
    assert rows['teacher']['case_ids'] == ['demo-case']


def test_kst_calendar_day_boundaries(env):
    client, creds, app, path = env
    insert_activity(path, 'demo-school', 'demo-case', 'teacher', '2026-10-30T14:59:59+00:00', 60)  # 23:59:59 KST
    insert_activity(path, 'demo-school', 'demo-case', 'teacher', '2026-10-30T15:00:00+00:00', 120)  # 00:00 KST next day
    first = dashboard(client, creds, **{'from': '2026-10-30', 'to': '2026-10-30'}).json()
    second = dashboard(client, creds, **{'from': '2026-10-31', 'to': '2026-10-31'}).json()
    assert first['staff_activity'][0]['recorded_seconds'] == 60
    assert second['staff_activity'][0]['recorded_seconds'] == 120
    assert first['period']['timezone'] == 'Asia/Seoul'


def test_other_school_data_is_not_aggregated_or_visible(env):
    client, creds, app, path = env
    db = sqlite3.connect(path)
    db.execute("INSERT INTO cases(id,school_id,title,owner_id,status,version) VALUES ('other-case','other-school','[가상] 다른 학교','other-admin','OPEN',1)")
    db.commit()
    db.close()
    insert_activity(path, 'other-school', 'other-case', 'other-admin', '2026-10-30T01:00:00+00:00', 999)
    insert_activity(path, 'demo-school', 'demo-case', 'teacher', '2026-10-30T01:00:00+00:00', 30)
    params = {'from': '2026-10-30', 'to': '2026-10-30'}
    own = dashboard(client, creds, **params).json()
    foreign = dashboard(client, creds, 'other-admin', **params).json()
    assert [row['staff_id'] for row in own['staff_activity']] == ['teacher']
    assert [row['staff_id'] for row in foreign['staff_activity']] == ['other-admin']
    assert 'other-case' not in str(own) and 'demo-case' not in str(foreign)
    # Another school's case cannot receive an activity either.
    denied = client.post('/api/cases/other-case/activities', headers=auth(creds), json={
        'expected_version': 1, 'staff_id': 'admin', 'kind': 'CALLBACK', 'occurred_at': '2026-10-30T10:00:00+09:00'})
    assert denied.status_code == 404


def test_teacher_activity_rules_and_append_only(env):
    client, creds, app, path = env
    assert log(client, creds, 'teacher', staff_id='admin').status_code == 403
    assert log(client, creds, staff_id='outsider').status_code == 422  # active member, not on this case
    naive = log(client, creds, occurred_at='2026-10-30T10:00:00')
    assert naive.status_code == 422 and naive.json()['code'] == 'INVALID_TIME'
    assert log(client, creds, duration_seconds=-5).status_code == 422
    assert log(client, creds, 'teacher').status_code == 201
    assert log(client, creds, staff_id='admin', kind='TASK_WORK').status_code == 201
    mine = client.get('/api/cases/demo-case/activities', headers=auth(creds, 'teacher')).json()
    everyone = client.get('/api/cases/demo-case/activities', headers=auth(creds, 'admin')).json()
    assert [item['staff_id'] for item in mine] == ['teacher'] and len(everyone) == 2
    db = sqlite3.connect(path)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE activity_logs SET duration_seconds=1")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('DELETE FROM activity_logs')
    db.close()


def test_support_waiting_counts_are_current_and_scoped(env):
    client, creds, app, path = env
    db = sqlite3.connect(path)
    db.execute("INSERT INTO support_requests(id,case_id,requester_id,coordinator_id,type,reason,status,created_at) "
               "VALUES (?,?,?,?,?,?,?,?)", (uid(), 'demo-case', 'teacher', 'admin', 'ATTEND', '[가상] 동석 요청', 'REQUESTED', now()))
    db.commit()
    db.close()
    result = dashboard(client, creds).json()
    assert result['support']['unacknowledged_now'] == 1
    assert result['support']['unacknowledged_case_ids'] == ['demo-case']
    assert result['support']['requested_in_period'] == {'REQUESTED': 1}
    assert dashboard(client, creds, 'other-admin').json()['support']['unacknowledged_now'] == 0


def test_invalid_period_is_rejected(env):
    client, creds, *_ = env
    assert dashboard(client, creds, **{'from': '2026-11-02', 'to': '2026-11-01'}).status_code == 422
    assert dashboard(client, creds, **{'from': 'yesterday'}).status_code == 422


def test_staff_detail_distinguishes_exposure_duration_and_current_queue(env):
    client,creds,app,path=env
    assert log(client,creds,duration_seconds=600).status_code==201
    assert log(client,creds,kind='TASK_WORK').status_code==201
    with app.state.db.transaction() as db:
        db.execute("INSERT INTO tasks(id,case_id,type,assignee_id,requester_id,question,callback_needed,status,created_at) VALUES ('waiting','demo-case','FACT_CHECK','teacher','admin','가상 확인','NOT_REQUIRED','REQUESTED','2026-10-29T00:00:00+00:00')")
    result=dashboard(client,creds,**{'from':'2026-10-30','to':'2026-10-30'}).json()
    teacher=next(s for s in result['staff_detail'] if s['staff_id']=='teacher')
    assert teacher['linked_cases']==1 and teacher['contact_count']==1
    assert teacher['recorded_seconds']==600 and teacher['average_recorded_case_seconds']==600
    assert teacher['missing_duration']==1 and teacher['recording_coverage']==50
    assert teacher['pending_tasks_now']==1 and teacher['oldest_wait_seconds']>0
    assert teacher['daily'][0]['date']=='2026-10-30'
    empty=next(s for s in result['staff_detail'] if s['staff_id']=='outsider')
    assert empty['recorded_seconds'] is None and empty['recording_coverage'] is None
    assert not {'score','rank'}&set(teacher)


def test_dashboard_fixtures_are_idempotent_and_explicitly_fictional(env):
    from backend.seed_support import seed_support
    from backend.seed_patterns import seed_patterns
    from backend.seed_dashboard import seed_dashboard
    client,creds,app,path=env
    seed_support(path)
    seed_patterns(path)
    seed_dashboard(path)
    seed_dashboard(path)
    with app.state.db.transaction() as db:
        assert db.execute("SELECT count(*) FROM activity_logs WHERE id LIKE 'demo-dashboard-%'").fetchone()[0]==8
        assert db.execute("SELECT count(*) FROM tasks WHERE id LIKE 'demo-dashboard-%'").fetchone()[0]==3
        assert db.execute("SELECT count(*) FROM activity_logs WHERE note LIKE '[가상 시연]%'").fetchone()[0]==15
        assert db.execute("SELECT count(*) FROM tasks WHERE id LIKE 'demo-support-task-%'").fetchone()[0]==6
    rows={s['staff_id']:s for s in dashboard(client,creds).json()['staff_detail']}
    assert len(rows)==8
    for staff in ('admin','deputy','academic-head','office-head','life-head','work-support'):
        assert rows[staff]['entries']>0
        assert rows[staff]['pending_tasks_now']==1
        assert rows[staff]['linked_cases']>0
    assert rows['deputy']['missing_duration']==1


def test_include_staff_keeps_active_members_without_activity(env):
    from backend.seed_support import seed_support
    client,creds,app,path=env
    seed_support(path)
    with app.state.db.transaction() as db:
        db.execute("UPDATE memberships SET active=0 WHERE user_id='work-support'")
    rows={s['staff_id']:s for s in dashboard(client,creds,**{'from':'2020-01-01','to':'2020-01-01'}).json()['staff_detail']}
    assert len(rows)==7 and 'work-support' not in rows
    assert rows['office-head']['recorded_seconds'] is None
    assert rows['office-head']['entries']==0
