"""Clearly labelled fictional activity and queue records for the dashboard demo."""
from datetime import datetime,timedelta,timezone
from .db import Database,now,audit
from .demo import seeded
from .access import DomainError

# Stable keys also identify these fixtures when inserted through the deployed API.
SUPPORT_SAMPLES = (
    ('admin', 5, 'SUPPORT_ACTION', 1200, '학교 공식 답변 검토·승인'),
    ('deputy', 3, 'COUNSEL', 1500, '담임 보호를 위한 관리자 동석 상담'),
    ('academic-head', 1, 'TASK_WORK', 900, '생활지도 기준과 학교 업무분장 확인'),
    ('office-head', 7, 'TASK_WORK', 600, '홈페이지 사진 공개 동의·비공개 절차 확인'),
    ('life-head', 4, 'COUNSEL', 1800, '새 자료에 대한 학생 생활지도 사실확인'),
    ('work-support', 6, 'CALLBACK', 480, '학교 명의 답변 전달 여부 확인'),
    ('deputy', 4, 'SUPPORT_ACTION', None, '추가 자료 검토 협의 · 시간 미기록'),
)
SUPPORT_TASKS = (
    ('admin', 5, 'FOLLOW_UP', '학교 공식 답변의 표현과 근거를 최종 검토해 주세요.'),
    ('deputy', 3, 'COUNSEL', '교사 동석 상담 일정과 학교 대응 창구를 확인해 주세요.'),
    ('academic-head', 1, 'FACT_CHECK', '수업 중 생활지도 기준과 업무분장을 확인해 주세요.'),
    ('office-head', 7, 'FACT_CHECK', '홈페이지 사진 게시 동의와 비공개 처리 절차를 확인해 주세요.'),
    ('life-head', 4, 'FACT_CHECK', '새 자료와 기존 수업 기록을 대조해 사실만 회신해 주세요.'),
    ('work-support', 6, 'FOLLOW_UP', '이전 학교 답변의 전달 일시와 추가 요구 유무를 확인해 주세요.'),
)


def seed_dashboard(path):
    with Database(path).transaction() as db:
        try: seeded(db)
        except DomainError: return
        for index,(staff,number,kind,duration,note) in enumerate(SUPPORT_SAMPLES):
            case_id=f'demo-pattern-{number:02d}'
            marker=f'[가상 시연·지원-{index:02d}]'
            if db.execute('SELECT 1 FROM activity_logs WHERE case_id=? AND substr(note,1,?)=?',(case_id,len(marker),marker)).fetchone(): continue
            if not db.execute('SELECT 1 FROM cases WHERE id=?',(case_id,)).fetchone(): continue
            if not db.execute("SELECT 1 FROM memberships WHERE school_id='demo-school' AND user_id=? AND active=1",(staff,)).fetchone(): continue
            db.execute('INSERT OR IGNORE INTO case_participants(case_id,user_id) VALUES (?,?)',(case_id,staff))
            db.execute("INSERT OR IGNORE INTO activity_logs(id,case_id,school_id,staff_id,recorded_by,kind,occurred_at,duration_seconds,note,created_at) VALUES (?,?,'demo-school',?,'admin',?,?,?,?,?)",
                       (f'demo-support-activity-{index:02d}',case_id,staff,kind,(datetime.now(timezone.utc)-timedelta(days=1,hours=index)).isoformat(),duration,'[가상 시연] '+note+' · 실제 활동 기록 아님.',now()))
        for index,(staff,number,kind,question) in enumerate(SUPPORT_TASKS):
            case_id=f'demo-pattern-{number:02d}'
            identity=f'demo-support-task-{index:02d}'
            marker=f'[가상 시연·지원업무-{index:02d}]'
            if db.execute('SELECT 1 FROM tasks WHERE case_id=? AND substr(question,1,?)=?',(case_id,len(marker),marker)).fetchone(): continue
            case=db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
            if not case or db.execute('SELECT 1 FROM tasks WHERE id=?',(identity,)).fetchone(): continue
            if not db.execute("SELECT 1 FROM memberships WHERE school_id='demo-school' AND user_id=? AND active=1",(staff,)).fetchone(): continue
            db.execute("INSERT INTO tasks(id,case_id,type,assignee_id,requester_id,question,callback_needed,status,created_at) VALUES (?,?,?,?,'admin',?,'NOT_REQUIRED','REQUESTED',?)",
                       (identity,case_id,kind,staff,'[가상 시연] '+question,(datetime.now(timezone.utc)-timedelta(hours=4+index)).isoformat()))
            version=case['version']+1
            db.execute('UPDATE cases SET version=? WHERE id=?',(version,case_id))
            audit(db,{'user_id':'admin'},case_id,'DEMO_SUPPORT_TASK_CREATED',version,{'fictional':True,'task_id':identity})
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
