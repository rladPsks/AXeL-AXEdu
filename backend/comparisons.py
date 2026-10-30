"""School-configured candidates and explicit, reversible human case relations."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime, Field, model_validator, field_validator

from .access import accessible_case, admin, authenticate, fail
from .commands import mutate
from .coordination import SchoolCommand, school_command, utc
from .db import audit, now, uid
from .evidence import documents
from .models import Command, Identifier, Text

router=APIRouter()


class ProfileUpdate(Command):
    person_key:Identifier|None=None
    issue_key:Identifier|None=None
    received_at:AwareDatetime

    @field_validator('received_at')
    @classmethod
    def date_range(cls,value):
        if value.year<1970:
            raise ValueError('Comparison dates must be 1970 or later')
        return value

    @model_validator(mode='after')
    def identifiable(self):
        if not self.person_key and not self.issue_key:
            raise ValueError('At least one opaque school-local comparison key is needed')
        return self


class RepeatSettings(SchoolCommand):
    window_days:int=Field(ge=1,le=3650)
    minimum_count:int=Field(ge=2,le=1000)
    response_delay_hours:int|None=Field(default=None,ge=1,le=8760)


class RelationCreate(Command):
    related_case_id:Identifier
    expected_related_version:int=Field(ge=1)
    previous_relation_id:Identifier|None=None
    state:Literal['LINKED','SEPARATED']
    basis:Literal['SAME_PERSON','SAME_ISSUE','BOTH']
    reason:Text


def settings(db,school_id):
    row=db.execute('SELECT * FROM repeat_review_settings WHERE school_id=?',(school_id,)).fetchone()
    return {**dict(row),'configured':True} if row else {'configured':False,'window_days':None,'minimum_count':None,'response_delay_hours':None}


@router.get('/api/school/repeat-settings')
def get_settings(request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        from .coordination import policy
        return {**settings(db,actor['school_id']),'settings_version':policy(db,actor['school_id'])['version']}


@router.put('/api/school/repeat-settings')
def put_settings(body:RepeatSettings,request:Request):
    def operation(db,actor):
        db.execute('INSERT INTO repeat_review_settings(school_id,window_days,minimum_count,response_delay_hours) VALUES (?,?,?,?) '
                   'ON CONFLICT(school_id) DO UPDATE SET window_days=excluded.window_days,minimum_count=excluded.minimum_count,response_delay_hours=excluded.response_delay_hours',
                   (actor['school_id'],body.window_days,body.minimum_count,body.response_delay_hours))
        return {'window_days':body.window_days,'minimum_count':body.minimum_count,'response_delay_hours':body.response_delay_hours}
    return school_command(request,body,'REPEAT_SETTINGS_UPDATED',operation)


@router.put('/api/cases/{case_id}/comparison-profile')
def put_profile(case_id:str,body:ProfileUpdate,request:Request):
    def operation(db,actor,case):
        admin(actor)
        db.execute('INSERT INTO case_comparison_profiles(case_id,person_key,issue_key,received_at,updated_by,updated_at) VALUES (?,?,?,?,?,?) '
                   'ON CONFLICT(case_id) DO UPDATE SET person_key=excluded.person_key,issue_key=excluded.issue_key,received_at=excluded.received_at,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
                   (case_id,body.person_key,body.issue_key,utc(body.received_at),actor['user_id'],now()))
        return {'profile_recorded':True,'person_key':body.person_key,'issue_key':body.issue_key,'received_at':utc(body.received_at)}
    return mutate(request,case_id,body,'CASE_COMPARISON_PROFILE_UPDATED',operation)


def relations(db,case_id):
    return [dict(row) for row in db.execute('SELECT r.* FROM case_relation_events r WHERE (left_case_id=? OR right_case_id=?) '
                'AND revision=(SELECT MAX(x.revision) FROM case_relation_events x WHERE x.left_case_id=r.left_case_id AND x.right_case_id=r.right_case_id) '
                'ORDER BY created_at DESC,id',(case_id,case_id))]


@router.post('/api/cases/{case_id}/relations',status_code=201)
def record_relation(case_id:str,body:RelationCreate,request:Request):
    def operation(db,actor,case):
        admin(actor)
        if case_id==body.related_case_id:
            fail(422,'SELF_CASE_RELATION','서로 다른 민원을 선택하세요.')
        other=accessible_case(db,actor,body.related_case_id)
        if other['version']!=body.expected_related_version:
            fail(409,'RELATED_VERSION_CONFLICT','비교 민원의 최신 버전을 조회하세요.')
        if other['status']=='CLOSED':
            fail(409,'RELATED_CASE_CLOSED','비교 민원을 재개한 뒤 연결을 변경하세요.')
        left,right=sorted((case_id,body.related_case_id))
        previous=db.execute('SELECT * FROM case_relation_events WHERE left_case_id=? AND right_case_id=? ORDER BY revision DESC LIMIT 1',(left,right)).fetchone()
        if body.previous_relation_id!=(previous['id'] if previous else None):
            fail(409,'RELATION_VERSION_CONFLICT','최신 연결 판단을 확인하세요.')
        relation_id=uid()
        db.execute('INSERT INTO case_relation_events(id,left_case_id,right_case_id,revision,state,basis,reason,recorded_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                   (relation_id,left,right,previous['revision']+1 if previous else 1,body.state,body.basis,body.reason,actor['user_id'],now()))
        db.execute('UPDATE cases SET version=version+1 WHERE id=?',(other['id'],))
        audit(db,actor,other['id'],'CASE_COMPARISON_RELATION_CHANGED',other['version']+1,{'relation_id':relation_id,'state':body.state})
        return {'relation_id':relation_id,'state':body.state,'related_case_version':other['version']+1}
    return mutate(request,case_id,body,'CASE_COMPARISON_RELATION_CHANGED',operation,201)


@router.get('/api/cases/{case_id}/comparison')
def comparison(case_id:str,request:Request,after:str='',limit:int=Query(default=30,ge=1,le=100)):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        accessible_case(db,actor,case_id)
        profile=db.execute('SELECT * FROM case_comparison_profiles WHERE case_id=?',(case_id,)).fetchone()
        configured=settings(db,actor['school_id'])
        candidates=[]
        count=0
        if profile:
            lower=utc(datetime.fromisoformat(profile['received_at'])-timedelta(days=configured['window_days'])) if configured['configured'] else None
            args=(actor['school_id'],case_id,profile['person_key'],profile['person_key'],profile['issue_key'],profile['issue_key'],lower,lower,profile['received_at'])
            where='c.school_id=? AND c.id!=? AND ((? IS NOT NULL AND p.person_key=?) OR (? IS NOT NULL AND p.issue_key=?)) AND (? IS NULL OR p.received_at>=?) AND p.received_at<=?'
            count=db.execute('SELECT COUNT(*) FROM case_comparison_profiles p JOIN cases c ON c.id=p.case_id WHERE '+where,args).fetchone()[0]
            rows=db.execute('SELECT c.id,c.title,c.status,c.version,p.person_key,p.issue_key,p.received_at FROM case_comparison_profiles p JOIN cases c ON c.id=p.case_id WHERE '+where+' AND c.id>? ORDER BY c.id LIMIT ?',(*args,after,limit+1)).fetchall()
            for row in rows[:limit]:
                matches=[]
                if profile['person_key'] and profile['person_key']==row['person_key']:
                    matches.append('SAME_PERSON')
                if profile['issue_key'] and profile['issue_key']==row['issue_key']:
                    matches.append('SAME_ISSUE')
                candidates.append({key:row[key] for key in ('id','title','status','version','received_at')}|{'matches':matches})
        else:
            rows=[]
        return {'profile':dict(profile) if profile else None,'policy':configured,'candidates':candidates,
                'candidate_count':count,'count_including_current':count+int(profile is not None),
                'review_threshold_met':(count+1>=configured['minimum_count']) if configured['configured'] and profile else None,
                'relations':relations(db,case_id),'next_cursor':rows[limit-1]['id'] if len(rows)>limit else None}


@router.get('/api/cases/{case_id}/compare/{related_case_id}')
def compare_pair(case_id:str,related_case_id:str,request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        current=accessible_case(db,actor,case_id)
        other=accessible_case(db,actor,related_case_id)
        if case_id==related_case_id:
            fail(422,'SELF_CASE_RELATION','서로 다른 민원을 선택하세요.')
        def evidence(case):
            versions=documents(db,actor,case['id'])
            latest={}
            for version in versions:
                if version['document_id'] not in latest or latest[version['document_id']]['revision']<version['revision']:
                    latest[version['document_id']]=version
            intake=[item for item in latest.values() if item['kind']=='INTAKE']
            replies=[item for item in latest.values() if item['kind']=='RESPONSE']
            criteria=settings(db,actor['school_id'])
            received=max((item['occurred_at'] for item in intake),default=None)
            delivered=bool(received and any(item['delivery_state']=='DELIVERED' and item['occurred_at']>=received for item in replies))
            review_due=None
            if received and criteria['response_delay_hours']:
                review_due=(datetime.now(timezone.utc)-datetime.fromisoformat(received)).total_seconds()>=criteria['response_delay_hours']*3600 and not delivered
            return {'case':dict(case),'documents':versions,
                    'response_review':{'review_due_from_records':review_due,'delivered_response_recorded':delivered,'latest_intake_at':received,
                                       'notice':'사람이 저장한 답변 전달 기록에 따른 재확인 표시이며 실제 미응답·법정 기한 판단이 아닙니다.'},
                    'tasks':[dict(row) for row in db.execute('SELECT * FROM tasks WHERE case_id=? ORDER BY created_at,id',(case['id'],))],
                    'support_requests':[dict(row) for row in db.execute('SELECT * FROM support_requests WHERE case_id=? ORDER BY created_at,id',(case['id'],))]}
        left,right=sorted((case_id,related_case_id))
        history=[dict(row) for row in db.execute('SELECT * FROM case_relation_events WHERE left_case_id=? AND right_case_id=? ORDER BY revision DESC',(left,right))]
        return {'current':evidence(current),'related':evidence(other),'relation_history':history,
                'notice':'저장된 기록을 대조합니다. 답변 기록이 없다는 이유만으로 실제 미응답을 확정하지 않습니다.'}
