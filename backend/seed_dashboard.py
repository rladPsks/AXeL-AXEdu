"""Clearly labelled fictional activity and queue records for the dashboard demo."""
from datetime import datetime,timedelta,timezone
from .db import Database,now,audit
from .demo import seeded
from .access import DomainError


def seed_dashboard(path):
    with Database(path).transaction() as db:
        try: seeded(db)
        except DomainError: return
        samples=[('teacher',1,'DIRECT_CONTACT',600),('teacher',2,'CALLBACK',900),('teacher',3,'COUNSEL',None),('teacher',4,'TASK_WORK',1800),('teacher',5,'CALLBACK',1200),('outsider',4,'COUNSEL',1200),('outsider',7,'TASK_WORK',600),('outsider',7,'DIRECT_CONTACT',None)]
        for index,(staff,number,kind,duration) in enumerate(samples):
            case_id=f'demo-pattern-{number:02d}'
            if not db.execute('SELECT 1 FROM cases WHERE id=?',(case_id,)).fetchone(): continue
            received=db.execute('SELECT received_at FROM case_intakes WHERE case_id=?',(case_id,)).fetchone()[0]
            occurred=datetime.fromisoformat(received)+timedelta(hours=index+1)
            db.execute('INSERT OR IGNORE INTO case_participants(case_id,user_id) VALUES (?,?)',(case_id,staff))
            db.execute('INSERT OR IGNORE INTO activity_logs(id,case_id,school_id,staff_id,recorded_by,kind,occurred_at,duration_seconds,note,created_at) VALUES (?,?,\'demo-school\',?,\'admin\',?,?,?,?,?)',(f'demo-dashboard-activity-{index:02d}',case_id,staff,kind,occurred.isoformat(),duration,'[가상 시연] 교사별 노출·업무시간 집계용 기록. 실제 상담/근무 기록 아님.',now()))
        for index,(staff,number,days) in enumerate([('teacher',3,3),('teacher',6,1),('outsider',7,0.5)]):
            identity=f'demo-dashboard-task-{index}'
            case_id=f'demo-pattern-{number:02d}'
            case=db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
            if not case or db.execute('SELECT 1 FROM tasks WHERE id=?',(identity,)).fetchone(): continue
            db.execute("INSERT INTO tasks(id,case_id,type,assignee_id,requester_id,question,callback_needed,status,created_at) VALUES (?,?,'FACT_CHECK',?,'admin','[가상 시연] 이전 안내 및 학생 상황 확인','NOT_REQUIRED','REQUESTED',?)",(identity,case_id,staff,(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()))
            version=case['version']+1
            db.execute('UPDATE cases SET version=? WHERE id=?',(version,case_id))
            audit(db,{'user_id':'admin'},case_id,'DEMO_DASHBOARD_TASK_CREATED',version,{'fictional':True,'task_id':identity,'reason':'교사별 대기 업무 시연용 가상 요청'})
