"""Visible L1–L3 workspaces over the shared, school-scoped case ledger."""
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Request
from pydantic import Field, model_validator
from .access import accessible_case, admin, authenticate, fail
from .commands import mutate
from .db import now, uid
from .models import Command, Text
from .comparisons import settings
from .decisions import latest as latest_decision, read_decision, serialize, require_current_decision
from agent.history_agent import compare_case_text

router = APIRouter()
KINDS = Literal['REPORT', 'RESPONSE', 'TRANSLATION']


def log(db, actor, case, action, payload):
    db.execute('INSERT INTO audit_events(id,case_id,actor_id,action,previous_version,new_version,created_at,payload) VALUES (?,?,?,?,?,?,?,?)',
               (uid(),case['id'],actor['user_id'],action,case['version'],case['version'],now(),json.dumps(payload,ensure_ascii=False)))


def delivered(db, case_id):
    return bool(db.execute("SELECT 1 FROM case_document_versions v JOIN case_documents d ON d.id=v.document_id WHERE d.case_id=? AND d.kind='RESPONSE' AND v.delivery_state='DELIVERED' AND v.revision=(SELECT MAX(x.revision) FROM case_document_versions x WHERE x.document_id=d.id)", (case_id,)).fetchone())


@router.get('/api/school/complainant-patterns')
def complainant_patterns(request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        admin(actor)
        policy = settings(db,actor['school_id'])
        days = policy['window_days'] or 30
        threshold = policy['minimum_count'] or 3
        lower = (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
        rows = db.execute('SELECT c.id,c.title,c.status,c.version,p.person_key,p.issue_key,p.received_at,i.complainant_name,i.raw_text,i.complaint_type FROM cases c JOIN case_comparison_profiles p ON p.case_id=c.id LEFT JOIN case_intakes i ON i.case_id=c.id WHERE c.school_id=? AND p.person_key IS NOT NULL AND p.received_at>=? ORDER BY p.received_at,c.id', (actor['school_id'],lower)).fetchall()
        groups = defaultdict(list)
        for row in rows:
            groups[row['person_key']].append(dict(row))
        result=[]
        for person, records in groups.items():
            issues=Counter(r['issue_key'] for r in records if r['issue_key'])
            previous={}
            for row in records:
                prior=previous.get(row['issue_key']) if row['issue_key'] else None
                comparison=compare_case_text(row['raw_text'] or '', prior['raw_text'] or '') if prior else None
                row['response_recorded']=delivered(db,row['id'])
                row['signals']=[]
                if prior:
                    prior_delivered_before=db.execute("SELECT 1 FROM case_document_versions v JOIN case_documents d ON d.id=v.document_id WHERE d.case_id=? AND d.kind='RESPONSE' AND v.delivery_state='DELIVERED' AND v.occurred_at<=? AND v.revision=(SELECT MAX(x.revision) FROM case_document_versions x WHERE x.document_id=d.id)",(prior['id'],row['received_at'])).fetchone()
                    if not prior_delivered_before: row['signals'].append('이전 민원 답변 전달 기록 없음 · 재문의 가능')
                    if comparison['has_new_information']: row['signals'].append('새 사실·요구 후보 · 내용 대조 필요')
                    if comparison['similarity']>=0.55: row['signals'].append('동일 사안 유사 내용')
                    row['compare_case_id']=prior['id']
                else:
                    row['signals'].append('새 사안 · 같은 민원인이라는 이유만으로 반복 판정하지 않음')
                row['comparison']=comparison
                previous[row['issue_key']]=row
            result.append({'person_key':person,'display_name':records[-1]['complainant_name'] or person,'count':len(records),'issue_count':len(issues),'repeat_candidate':max(issues.values(),default=0)>=threshold,'unanswered_count':sum(not r['response_recorded'] for r in records),'cases':records})
        result.sort(key=lambda r:(-r['count'],r['person_key']))
        unlinked=db.execute('SELECT COUNT(*) FROM case_intakes i JOIN cases c ON c.id=i.case_id LEFT JOIN case_comparison_profiles p ON p.case_id=c.id WHERE c.school_id=? AND p.person_key IS NULL',(actor['school_id'],)).fetchone()[0]
        return {'window_days':days,'minimum_count':threshold,'configured':policy['configured'],'groups':result,'unlinked_count':unlinked,'notice':'확인된 학교 내부 식별키로 묶습니다. 이름이나 횟수만으로 악성·부당 민원이나 이관을 확정하지 않습니다. 답변 미기록은 실제 미응답 확정과 다릅니다.'}


@router.get('/api/cases/{case_id}/full-history')
def full_history(case_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        accessible_case(db,actor,case_id)
        events=[{**dict(r),'payload':json.loads(r['payload']),'source':'처리 기록'} for r in db.execute('SELECT * FROM audit_events WHERE case_id=?',(case_id,))]
        for r in db.execute('SELECT e.* FROM agent_run_events e JOIN agent_runs a ON a.id=e.run_id WHERE a.case_id=?',(case_id,)):
            events.append({'id':r['id'],'action':'AI '+r['status']+' · '+r['step'],'actor_id':r['actor_id'] or 'AI','created_at':r['created_at'],'source':'AI 실행','payload':json.loads(r['detail'] or '{}')})
        for r in db.execute('SELECT * FROM activity_logs WHERE case_id=?',(case_id,)):
            events.append({'id':r['id'],'action':'활동 · '+r['kind'],'actor_id':r['recorded_by'],'created_at':r['created_at'],'source':'활동 기록','payload':{'note':r['note'],'occurred_at':r['occurred_at'],'duration_seconds':r['duration_seconds']}})
        for r in db.execute('SELECT v.*,d.label FROM case_document_versions v JOIN case_documents d ON d.id=v.document_id WHERE d.case_id=?',(case_id,)):
            events.append({'id':r['id'],'action':'자료 · '+r['label'],'actor_id':r['recorded_by'],'created_at':r['created_at'],'source':'자료 버전','payload':{'content':r['content'],'provenance':r['provenance'],'occurred_at':r['occurred_at'],'revision':r['revision'],'delivery_state':r['delivery_state']}})
        for r in db.execute('SELECT * FROM comparison_inputs WHERE case_id=?',(case_id,)):
            events.append({'id':r['id'],'action':'COMPARISON_INPUT_PREPARED','actor_id':r['requested_by'],'created_at':r['created_at'],'source':'비교 자료','payload':{'related_case_id':r['related_case_id'],'case_version':r['case_version'],'related_case_version':r['related_case_version']}})
        return sorted(events,key=lambda e:(e['created_at'],e['id']),reverse=True)


def latest_product(db,case_id,kind):
    return db.execute('SELECT * FROM case_work_products WHERE case_id=? AND kind=? ORDER BY revision DESC LIMIT 1',(case_id,kind)).fetchone()


def product_json(row,case):
    return {**dict(row),'content':json.loads(row['content']),'stale':row['source_case_version']!=case['version']}


def report_text(db,case,intake,decision):
    workflow=json.loads(intake['workflow_json'] or '{}') if intake else {}
    lines=['교육지원청 지원·이관 검토 서류 (초안)', '', '민원: '+case['title'], '접수번호: '+case['id'], '', '1. 민원 개요', intake['raw_text'] if intake else case['title'], '', '2. 학교 확인·조치']
    for task in db.execute('SELECT * FROM tasks WHERE case_id=? ORDER BY created_at',(case['id'],)):
        lines.append(f"- {task['question']} / {task['status']} / {task['reply'] or '확인 중'}")
    lines += ['', '3. 관리자 지원 판단']
    if decision:
        saved=json.loads(decision['snapshot'])
        for key,title in [('reason','판단 사유'),('target','요청 기관'),('route','지원 경로'),('remaining_school_work','학교의 후속 의무')]: lines.append(title+': '+saved.get(key,''))
        for o in saved.get('observations',[]): lines.append(f"- {o['kind']}: {o['detail']} (출처: {o['source_id']})")
    else: lines.append('관리자 판단 미등록 · 학교 지원·판단 탭에서 등록 필요')
    lines += ['', '4. 참고 근거']
    for e in workflow.get('tools',{}).get('rag',[]): lines.append(f"- {e.get('title') or e.get('source_id')} / {e.get('article') or e.get('pdf_page') or '위치 확인 필요'}: {e.get('text','')}")
    lines += ['', '5. 첨부 목록']
    for f in db.execute("SELECT filename FROM private_files WHERE case_id=? AND category!='AUDIO'",(case['id'],)): lines.append('- '+f['filename'])
    lines += ['', '6. 미확인 사항·후속 업무', '관할 기관의 실제 서식과 접수 경로를 확인하고 필요한 개인정보를 검토하세요.', '학교의 사실 확인·학생 보호·민원인 안내는 담당자가 계속 수행합니다.', '', '이 문서는 자동 제출되지 않습니다.']
    return '\n'.join(lines)


@router.get('/api/cases/{case_id}/work-products/{kind}')
def get_products(case_id: str, kind: KINDS, request: Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request); admin(actor)
        case=accessible_case(db,actor,case_id)
        intake=db.execute('SELECT * FROM case_intakes WHERE case_id=?',(case_id,)).fetchone()
        workflow=json.loads(intake['workflow_json'] or '{}') if intake else {}
        decision=latest_decision(db,case_id)
        decision_result=None
        if decision:
            row,actual,saved=read_decision(db,actor,decision['id'])
            decision_result=serialize(db,row,actual,saved,actor)
        if kind=='REPORT':
            initial={'text':report_text(db,case,intake,decision),'original':'','language':'ko'}
        elif kind=='TRANSLATION':
            language=workflow.get('multilingual',{})
            initial={'text':language.get('translated_text_ko') or (intake['raw_text'] if intake else ''),'original':intake['raw_text'] if intake else '', 'language':language.get('detected_language','ko')}
        else:
            run=db.execute("SELECT result FROM agent_runs WHERE case_id=? AND purpose='REVIEW_SUPPORT' AND result IS NOT NULL ORDER BY created_at DESC LIMIT 1",(case_id,)).fetchone()
            result=json.loads(run['result']) if run else {}
            draft=result.get('response_draft') or workflow.get('initial_response_draft') or ''
            initial={'text':draft,'original':draft,'language':'ko'}
        products=[product_json(r,case) for r in db.execute('SELECT * FROM case_work_products WHERE case_id=? AND kind=? ORDER BY revision DESC',(case_id,kind))]
        return {'initial':initial,'products':products,'decision':decision_result,'evidence':workflow.get('tools',{}).get('rag',[])}


class ProductSave(Command):
    previous_revision: int = Field(ge=0)
    content: dict[str, str]
    reason: Text
    @model_validator(mode='after')
    def content_check(self):
        if set(self.content)-{'text','original','language'} or not self.content.get('text','').strip() or any(len(v)>40000 for v in self.content.values()):
            raise ValueError('본문은 필수이며 필드당 40000자까지 가능합니다.')
        return self


class ProductTransition(Command):
    revision: int = Field(ge=1)
    action: Literal['APPROVED','DELIVERED','EXPORTED']
    reason: Text


def insert_product(db,actor,case,kind,content,revision,status,decision_id=None):
    identity=uid()
    db.execute('INSERT INTO case_work_products(id,case_id,kind,revision,content,source_case_version,recorded_case_version,status,decision_id,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
               (identity,case['id'],kind,revision,json.dumps(content,ensure_ascii=False),case['version'],case['version'],status,decision_id,actor['user_id'],now()))
    return identity


@router.post('/api/cases/{case_id}/work-products/{kind}')
def save_product(case_id: str,kind: KINDS,body: ProductSave,request: Request):
    def operation(db,actor,case):
        admin(actor)
        latest=latest_product(db,case_id,kind)
        if body.previous_revision != (latest['revision'] if latest else 0): fail(409,'PRODUCT_CONFLICT','최신 문서 버전을 확인하세요.')
        revision=body.previous_revision+1
        identity=insert_product(db,actor,case,kind,body.content,revision,'DRAFT')
        log(db,actor,case,kind+'_DRAFT_SAVED',{'product_id':identity,'revision':revision,'reason':body.reason})
        return {'product_id':identity,'revision':revision}
    return mutate(request,case_id,body,kind+'_DRAFT_SAVED',operation,advance_case=False)


@router.post('/api/cases/{case_id}/work-products/{kind}/transition')
def transition_product(case_id: str,kind: KINDS,body: ProductTransition,request: Request):
    def operation(db,actor,case):
        admin(actor)
        latest=latest_product(db,case_id,kind)
        if not latest or latest['revision']!=body.revision: fail(409,'PRODUCT_CONFLICT','최신 문서 버전을 확인하세요.')
        if latest['source_case_version']!=case['version']: fail(409,'STALE_PRODUCT','민원 기록이 변경되었습니다. 최신 기록으로 문서를 수정 저장하고 다시 검토하세요.')
        allowed = body.action=='APPROVED' and latest['status']=='DRAFT' or body.action=='DELIVERED' and kind=='RESPONSE' and latest['status']=='APPROVED' or body.action=='EXPORTED' and kind=='REPORT' and latest['status'] in ('APPROVED','EXPORTED')
        if not allowed: fail(409,'INVALID_TRANSITION','초안 저장과 승인 순서를 확인하세요.')
        decision_id=latest['decision_id']
        if kind=='REPORT':
            decision=latest_decision(db,case_id)
            if not decision: fail(409,'DECISION_REQUIRED','학교 지원·판단에서 지원 대상·사유·후속 의무를 먼저 기록하세요.')
            current=require_current_decision(db,actor,case,decision['id'])
            if current['snapshot']['decision_type'] not in ('EXTERNAL_SUPPORT','SPECIALIST_SUPPORT'): fail(409,'EXTERNAL_DECISION_REQUIRED','외부·전문 지원 판단을 먼저 검토하세요.')
            if decision_id and decision_id!=decision['id']: fail(409,'DECISION_CHANGED','지원 판단이 바뀌었습니다. 서류를 다시 작성하세요.')
            decision_id=decision['id']
        content=json.loads(latest['content'])
        product_case=case
        if kind=='TRANSLATION' and body.action=='APPROVED':
            product_case={**dict(case),'version':case['version']+1}
            intake=db.execute('SELECT workflow_json FROM case_intakes WHERE case_id=?',(case_id,)).fetchone()
            if not intake: fail(409,'INTAKE_REQUIRED','접수 원문이 필요합니다.')
            workflow=json.loads(intake['workflow_json'] or '{}')
            language=workflow.setdefault('multilingual',{})
            language.update({'translated_text_ko':content['text'],'detected_language':content.get('language','unknown'),'review_status':'APPROVED','reviewed_revision':body.revision+1,'reviewed_by':actor['user_id']})
            db.execute('UPDATE case_intakes SET workflow_json=? WHERE case_id=?',(json.dumps(workflow,ensure_ascii=False),case_id))
        identity=insert_product(db,actor,product_case,kind,content,body.revision+1,body.action,decision_id)
        if kind=='RESPONSE' and body.action=='DELIVERED':
            doc_id=uid()
            db.execute("INSERT INTO case_documents(id,case_id,kind,label,created_by,created_at) VALUES (?,?,'RESPONSE','승인 답변 전달 기록',?,?)",(doc_id,case_id,actor['user_id'],now()))
            db.execute("INSERT INTO case_document_versions(id,document_id,revision,content,provenance,occurred_at,delivery_state,recorded_by,created_at) VALUES (?,?,1,?,?,?,'DELIVERED',?,?)",(uid(),doc_id,content['text'],body.reason,now(),actor['user_id'],now()))
        log(db,actor,product_case,kind+'_'+body.action,{'product_id':identity,'revision':body.revision+1,'reason':body.reason,'decision_id':decision_id})
        return {'product_id':identity,'revision':body.revision+1,'text':content['text'] if body.action=='EXPORTED' else None}
    return mutate(request,case_id,body,kind+'_'+body.action,operation,advance_case=kind=='TRANSLATION' and body.action=='APPROVED')


def response_closure_guard(db,actor,case_id):
    intake=db.execute('SELECT 1 FROM case_intakes WHERE case_id=?',(case_id,)).fetchone()
    if intake and not delivered(db,case_id): return [{'code':'RESPONSE_DELIVERY_REQUIRED','message':'실질 답변의 전달 기록을 먼저 남기세요.'}]
    latest=latest_product(db,case_id,'RESPONSE')
    if latest and latest['status']!='DELIVERED': return [{'code':'RESPONSE_REVIEW_REQUIRED','message':'최신 답변을 승인하고 전달 기록을 남기세요.'}]
    return []
