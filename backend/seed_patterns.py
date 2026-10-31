"""Seven linked fictional inquiries: repeats, missing replies, new evidence, new issue."""
import json
from datetime import datetime,timedelta,timezone
from .db import Database,now,uid,audit
from .demo import seeded
from .access import DomainError
from .demo_narratives import PATTERN_SAMPLES
from agent.routing import route_case
from agent.draft import teacher_card


def seed_patterns(path):
    added=0
    base=datetime.now(timezone.utc)-timedelta(days=7)
    samples=PATTERN_SAMPLES
    with Database(path).transaction() as db:
        try: seeded(db)
        except DomainError: return 0
        db.execute("INSERT OR IGNORE INTO repeat_review_settings(school_id,window_days,minimum_count,response_delay_hours) VALUES ('demo-school',30,3,24)")
        for index,(title,raw,issue) in enumerate(samples,1):
            case_id=f'demo-pattern-{index:02d}'
            if db.execute('SELECT 1 FROM cases WHERE id=?',(case_id,)).fetchone(): continue
            received=(base+timedelta(days=index-1)).isoformat()
            summary='가상민원인 나○○의 '+title
            cls={'category':'EDU' if index<7 else 'ADMIN','nature':'COMPLAINT','urgency':'MID','is_informational':False,'summary_for_teacher':summary,'action_for_teacher':'학교의 기존 답변 전달 여부와 새로운 사실을 구분해 확인해 주세요.','infringement_flags':[],'classifier_mode':'DEMO_FIXTURE'}
            routing=route_case('fact_check',text=raw,classification=cls)
            workflow={'agent':{'classifier_mode':'DEMO_FIXTURE'},'teacher_card':teacher_card(summary,cls['action_for_teacher'],False),'tools':{'rag':[],'history':[]},'fixture':{'fictional':True,'scenario':title},'initial_response_draft':''}
            db.execute("INSERT INTO cases(id,school_id,title,owner_id,status,version) VALUES (?,'demo-school',?,'admin','OPEN',1)",(case_id,'[반복 시연] '+title))
            db.execute("INSERT INTO case_intakes(case_id,received_at,channel,complainant_name,student_name,complaint_type,related_people,incident_context,raw_text,source_type,classification_json,routing_json,created_by,created_at,workflow_json) VALUES (?,?,'homepage','가상민원인 나○○','가상학생 나○○',?,'[]','동일인을 확인한 가상 시연 사례',?,'DIRECT',?,?,'admin',?,?)",(case_id,received,title,raw,json.dumps(cls,ensure_ascii=False),json.dumps(routing,ensure_ascii=False),now(),json.dumps(workflow,ensure_ascii=False)))
            db.execute("INSERT INTO case_comparison_profiles(case_id,person_key,issue_key,received_at,updated_by,updated_at) VALUES (?,'demo-person-pattern',?,?,'admin',?)",(case_id,issue,received,now()))
            for user in ('admin','deputy','teacher'): db.execute('INSERT INTO case_participants(case_id,user_id) VALUES (?,?)',(case_id,user))
            audit(db,{'user_id':'admin'},case_id,'DEMO_PATTERN_CREATED',1,{'fictional':True,'reason':title,'occurred_at':received})
            def document(kind,label,content,at,state='NOT_APPLICABLE'):
                doc=uid()
                db.execute("INSERT INTO case_documents(id,case_id,kind,label,created_by,created_at) VALUES (?,?,?,?,'admin',?)",(doc,case_id,kind,label,now()))
                db.execute("INSERT INTO case_document_versions(id,document_id,revision,content,provenance,occurred_at,delivery_state,recorded_by,created_at) VALUES (?,?,1,?,'가상 시연용 기록 · 실제 발송·증거 아님',?,?,'admin',?)",(uid(),doc,content,at,state,now()))
            document('INTAKE','가상 접수 원문',raw,received)
            if index==4: document('EVIDENCE','가상 추가 자료','[가상] 학생 활동 기록: 이전 문의에 없던 쉬는 시간 상황에 관한 주장. 사실 확인 필요.',received)
            if index==5:
                document('RESPONSE','가상 학교 답변','[가상] 학교에서 수업 기록을 확인했습니다. 지도 기준과 확인된 상황을 안내하고 추가 상담을 제안했습니다.',(base+timedelta(days=4,hours=2)).isoformat(),'DELIVERED')
                audit(db,{'user_id':'admin'},case_id,'DEMO_RESPONSE_RECORDED',1,{'fictional':True,'reason':'시연상 서면 답변 전달 기록. 실제 외부 발송 아님.'})
            added+=1
    return added
