"""Versioned school configuration and availability-aware support routing."""
import json
from typing import Literal
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from .access import admin, authenticate, fail, member
from .commands import command_identity, replay_command, save_command
from .db import now, uid
from .models import Identifier, Text

router=APIRouter()


def utc(value):
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


def policy(db,school_id):
    row=db.execute('SELECT * FROM school_settings WHERE school_id=?',(school_id,)).fetchone()
    return dict(row) if row else {'school_id':school_id,'version':1,'duty_admin_id':None,
                                 'support_ack_minutes':60,'overdue_grace_minutes':0,'alerts_enabled':1}


def resolve_support(db,school_id,requested_id,at=None,exclude=()):
    at=at or now()
    settings=policy(db,school_id)
    candidates=[requested_id]
    if settings['duty_admin_id']:
        candidates.append(settings['duty_admin_id'])
    seen=set(exclude)
    while candidates:
        candidate=candidates.pop(0)
        if candidate in seen:
            continue
        seen.add(candidate)
        row=db.execute("SELECT * FROM memberships WHERE user_id=? AND school_id=? AND role='ADMIN' AND active=1",
                       (candidate,school_id)).fetchone()
        if row is None:
            continue
        absence=db.execute('SELECT substitute_id FROM staff_absences WHERE school_id=? AND user_id=? AND active=1 '
                           'AND starts_at<=? AND ends_at>?',(school_id,candidate,at,at)).fetchone()
        if absence:
            candidates.insert(0,absence['substitute_id'])
            continue
        return candidate, 'DIRECT' if candidate==requested_id else 'SUBSTITUTE'
    return requested_id, 'NO_AVAILABLE_SUBSTITUTE'


class SchoolCommand(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_settings_version:int=Field(ge=1)


class SettingsUpdate(SchoolCommand):
    duty_admin_id:Identifier|None=None
    support_ack_minutes:int=Field(default=60,ge=1,le=10080)
    overdue_grace_minutes:int=Field(default=0,ge=0,le=10080)
    alerts_enabled:bool=True


class AbsenceCreate(SchoolCommand):
    user_id:Identifier
    substitute_id:Identifier
    starts_at:AwareDatetime
    ends_at:AwareDatetime
    note:Text|None=None

    @field_validator('starts_at','ends_at')
    @classmethod
    def normalize(cls,value):
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def ordered(self):
        if self.starts_at>=self.ends_at or self.user_id==self.substitute_id:
            raise ValueError('Invalid absence range or self substitution')
        return self


class SettingRemoval(SchoolCommand):
    reason:Text


class ResponsibilityCreate(SchoolCommand):
    label:Identifier
    user_id:Identifier
    substitute_id:Identifier|None=None


class MemberUpdate(SchoolCommand):
    role:Literal['ADMIN','TEACHER']
    active:bool
    reason:Text


def school_command(request,body,action,operation,status=200):
    identity=command_identity(request,body)
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        previous=policy(db,actor['school_id'])
        replay=replay_command(db,actor,identity)
        if replay is not None:
            return replay
        if body.expected_settings_version!=previous['version']:
            fail(409,'SETTINGS_VERSION_CONFLICT','학교 설정의 최신 내용을 확인하세요.',current_settings_version=previous['version'])
        db.execute('INSERT OR IGNORE INTO school_settings(school_id) VALUES (?)',(actor['school_id'],))
        result=operation(db,actor)
        version=previous['version']+1
        db.execute('UPDATE school_settings SET version=? WHERE school_id=?',(version,actor['school_id']))
        db.execute('INSERT INTO school_audit_events(id,school_id,actor_id,action,previous_version,new_version,payload,created_at) VALUES (?,?,?,?,?,?,?,?)',
                   (uid(),actor['school_id'],actor['user_id'],action,previous['version'],version,json.dumps(result,ensure_ascii=False),now()))
        response={'settings_version':version,**result}
        save_command(db,actor,identity,response,status)
        return JSONResponse(response,status_code=status)


@router.get('/api/school/settings')
def settings(request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        result=policy(db,actor['school_id'])
        result['absences']=[dict(r) for r in db.execute('SELECT * FROM staff_absences WHERE school_id=? ORDER BY starts_at,id',(actor['school_id'],))]
        result['responsibilities']=[dict(r) for r in db.execute('SELECT * FROM school_responsibilities WHERE school_id=? ORDER BY label,id',(actor['school_id'],))]
        return result


@router.get('/api/school/members')
def members(request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        return [dict(r) for r in db.execute('SELECT user_id,role,active FROM memberships WHERE school_id=? ORDER BY user_id',(actor['school_id'],))]


@router.get('/api/school/settings/timeline')
def settings_timeline(request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        return [{**dict(row),'payload':json.loads(row['payload'])} for row in db.execute(
            'SELECT * FROM school_audit_events WHERE school_id=? ORDER BY new_version DESC LIMIT 100',(actor['school_id'],))]


@router.get('/api/school/contacts')
def contacts(request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        result=[]
        for row in db.execute('SELECT id,label,user_id,substitute_id FROM school_responsibilities WHERE school_id=? AND active=1 ORDER BY label,id',(actor['school_id'],)):
            item=dict(row)
            contact,routing=resolve_support(db,actor['school_id'],row['user_id'])
            item['support_contact_id']=contact if routing!='NO_AVAILABLE_SUBSTITUTE' else None
            result.append(item)
        return result


@router.put('/api/school/members/{user_id}')
def update_member(user_id:str,body:MemberUpdate,request:Request):
    def operation(db,actor):
        current=db.execute('SELECT * FROM memberships WHERE user_id=? AND school_id=?',(user_id,actor['school_id'])).fetchone()
        if current is None:
            fail(404,'RESOURCE_NOT_FOUND','학교 구성원을 찾을 수 없습니다.')
        if user_id==actor['user_id']:
            fail(403,'SELF_PERMISSION_CHANGE','자신의 권한 변경은 다른 학교 관리자에게 요청하세요.')
        if current['role']==body.role and current['active']==int(body.active):
            fail(409,'NO_PERMISSION_CHANGE','변경할 권한이나 활성 상태를 선택하세요.')
        pending={}
        if body.role!='ADMIN' or not body.active:
            pending['owners']=db.execute('SELECT COUNT(*) FROM cases WHERE school_id=? AND owner_id=?',(actor['school_id'],user_id)).fetchone()[0]
            pending['support_requests']=db.execute("SELECT COUNT(*) FROM support_requests s JOIN cases c ON c.id=s.case_id WHERE c.school_id=? AND s.coordinator_id=? AND s.status!='COMPLETED'",(actor['school_id'],user_id)).fetchone()[0]
            pending['handovers']=db.execute("SELECT COUNT(*) FROM handovers h JOIN cases c ON c.id=h.case_id WHERE c.school_id=? AND h.status='PENDING' AND (h.from_owner_id=? OR h.to_owner_id=?)",(actor['school_id'],user_id,user_id)).fetchone()[0]
            pending['duty']=int(policy(db,actor['school_id'])['duty_admin_id']==user_id)
        if not body.active:
            pending['tasks']=db.execute("SELECT COUNT(*) FROM tasks t JOIN cases c ON c.id=t.case_id WHERE c.school_id=? AND t.assignee_id=? AND t.status!='COMPLETED'",(actor['school_id'],user_id)).fetchone()[0]
            pending['responsibilities']=db.execute('SELECT COUNT(*) FROM school_responsibilities WHERE school_id=? AND active=1 AND (user_id=? OR substitute_id=?)',(actor['school_id'],user_id,user_id)).fetchone()[0]
        if not body.active or body.role!=current['role']:
            pending['absences']=db.execute('SELECT COUNT(*) FROM staff_absences WHERE school_id=? AND active=1 AND ends_at>? AND (user_id=? OR substitute_id=?)',(actor['school_id'],now(),user_id,user_id)).fetchone()[0]
        if any(pending.values()):
            fail(409,'RESPONSIBILITY_REMAINS','총괄·업무·지원·인계·당번·부재 설정의 남은 책임을 먼저 인계하거나 해제하세요.',pending=pending)
        db.execute('UPDATE memberships SET role=?,active=? WHERE user_id=? AND school_id=?',(body.role,int(body.active),user_id,actor['school_id']))
        db.execute('DELETE FROM sessions WHERE user_id=? AND school_id=?',(user_id,actor['school_id']))
        return {'user_id':user_id,'role':body.role,'active':int(body.active),'reason':body.reason,'sessions_revoked':True}
    return school_command(request,body,'MEMBER_PERMISSION_CHANGED',operation)


@router.put('/api/school/settings')
def update_settings(body:SettingsUpdate,request:Request):
    def operation(db,actor):
        if body.duty_admin_id:
            member(db,actor,body.duty_admin_id,'ADMIN')
        db.execute('UPDATE school_settings SET duty_admin_id=?,support_ack_minutes=?,overdue_grace_minutes=?,alerts_enabled=? WHERE school_id=?',
                   (body.duty_admin_id,body.support_ack_minutes,body.overdue_grace_minutes,int(body.alerts_enabled),actor['school_id']))
        return {'duty_admin_id':body.duty_admin_id,'support_ack_minutes':body.support_ack_minutes,
                'overdue_grace_minutes':body.overdue_grace_minutes,'alerts_enabled':body.alerts_enabled}
    return school_command(request,body,'SCHOOL_SETTINGS_UPDATED',operation)


@router.post('/api/school/absences',status_code=201)
def create_absence(body:AbsenceCreate,request:Request):
    def operation(db,actor):
        member(db,actor,body.user_id)
        role=db.execute('SELECT role FROM memberships WHERE user_id=? AND school_id=?',(body.user_id,actor['school_id'])).fetchone()['role']
        member(db,actor,body.substitute_id,role)
        start,end=utc(body.starts_at),utc(body.ends_at)
        if db.execute('SELECT 1 FROM staff_absences WHERE school_id=? AND user_id=? AND active=1 AND starts_at<? AND ends_at>?',
                      (actor['school_id'],body.user_id,end,start)).fetchone():
            fail(409,'ABSENCE_OVERLAP','겹치는 부재 일정이 있습니다.')
        absence_id=uid()
        db.execute('INSERT INTO staff_absences(id,school_id,user_id,substitute_id,starts_at,ends_at,note,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                   (absence_id,actor['school_id'],body.user_id,body.substitute_id,start,end,body.note,actor['user_id'],now()))
        return {'absence_id':absence_id,'user_id':body.user_id,'substitute_id':body.substitute_id}
    return school_command(request,body,'ABSENCE_CREATED',operation,201)


@router.post('/api/school/absences/{absence_id}/cancel')
def cancel_absence(absence_id:str,body:SettingRemoval,request:Request):
    def operation(db,actor):
        row=db.execute('SELECT active FROM staff_absences WHERE id=? AND school_id=?',(absence_id,actor['school_id'])).fetchone()
        if row is None:
            fail(404,'RESOURCE_NOT_FOUND','부재 설정을 찾을 수 없습니다.')
        if not row['active']:
            fail(409,'INVALID_TRANSITION','이미 취소한 부재 설정입니다.')
        db.execute('UPDATE staff_absences SET active=0,cancelled_by=?,cancellation_reason=? WHERE id=?',(actor['user_id'],body.reason,absence_id))
        return {'absence_id':absence_id,'active':0,'reason':body.reason}
    return school_command(request,body,'ABSENCE_CANCELLED',operation)


@router.post('/api/school/responsibilities',status_code=201)
def create_responsibility(body:ResponsibilityCreate,request:Request):
    def operation(db,actor):
        member(db,actor,body.user_id)
        if body.substitute_id:
            member(db,actor,body.substitute_id)
        item_id=uid()
        db.execute('INSERT INTO school_responsibilities(id,school_id,label,user_id,substitute_id) VALUES (?,?,?,?,?)',
                   (item_id,actor['school_id'],body.label,body.user_id,body.substitute_id))
        return {'responsibility_id':item_id,'label':body.label}
    return school_command(request,body,'RESPONSIBILITY_CREATED',operation,201)


@router.post('/api/school/responsibilities/{responsibility_id}/remove')
def remove_responsibility(responsibility_id:str,body:SettingRemoval,request:Request):
    def operation(db,actor):
        row=db.execute('SELECT active FROM school_responsibilities WHERE id=? AND school_id=?',(responsibility_id,actor['school_id'])).fetchone()
        if row is None:
            fail(404,'RESOURCE_NOT_FOUND','업무분장을 찾을 수 없습니다.')
        if not row['active']:
            fail(409,'INVALID_TRANSITION','이미 해제된 업무분장입니다.')
        db.execute('UPDATE school_responsibilities SET active=0 WHERE id=?',(responsibility_id,))
        return {'responsibility_id':responsibility_id,'active':0,'reason':body.reason}
    return school_command(request,body,'RESPONSIBILITY_REMOVED',operation)
