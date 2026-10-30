"""Task dates use separate commands so existing request models remain compatible."""
from datetime import timezone
from fastapi import APIRouter, Request
from pydantic import AwareDatetime, field_validator, model_validator
from .access import fail,admin,member,participate
from .commands import mutate, resource_case
from .coordination import utc
from .db import now
from .models import Command, Text,Identifier

router=APIRouter()


class ScheduleUpdate(Command):
    planned_start_at:AwareDatetime|None=None
    due_at:AwareDatetime|None=None
    reason:Text

    @field_validator('planned_start_at','due_at')
    @classmethod
    def normalize(cls,value):
        return value.astimezone(timezone.utc) if value else None

    @model_validator(mode='after')
    def ordered(self):
        if self.planned_start_at and self.due_at and self.planned_start_at>self.due_at:
            raise ValueError('Start must precede due time')
        return self


class TaskReassign(Command):
    assignee_id:Identifier
    reason:Text


@router.post('/api/tasks/{task_id}/reassign')
def reassign_task(task_id:str,body:TaskReassign,request:Request):
    from .notifications import enqueue
    case_id=resource_case(request,'tasks',task_id)
    def operation(db,actor,case):
        admin(actor)
        member(db,actor,body.assignee_id)
        task=db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
        if task['status']=='COMPLETED':
            fail(409,'TASK_ALREADY_COMPLETED','완료된 업무는 다시 배정할 수 없습니다.')
        if task['assignee_id']==body.assignee_id:
            fail(422,'SAME_ASSIGNEE','다른 수행자를 선택하세요.')
        db.execute("UPDATE tasks SET assignee_id=?,status='REQUESTED',reply=NULL WHERE id=?",(body.assignee_id,task_id))
        participate(db,case_id,body.assignee_id)
        for recipient in {body.assignee_id,task['assignee_id'],task['requester_id']}-{actor['user_id']}:
            enqueue(db,case_id,recipient,'TASK_REASSIGNED',task_id,f'task:{task_id}:reassign:{case["version"]+1}')
        return {'task_id':task_id,'previous_assignee_id':task['assignee_id'],'assignee_id':body.assignee_id,
                'status':'REQUESTED','reason':body.reason,'owner_id':case['owner_id']}
    return mutate(request,case_id,body,'TASK_REASSIGNED',operation)


@router.put('/api/tasks/{task_id}/schedule')
def update_schedule(task_id:str,body:ScheduleUpdate,request:Request):
    from .notifications import enqueue
    case_id=resource_case(request,'tasks',task_id)
    def operation(db,actor,case):
        task=db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
        if actor['role']!='ADMIN' and actor['user_id']!=task['assignee_id']:
            fail(403,'TASK_FORBIDDEN','수행자 또는 관리자가 일정을 변경할 수 있습니다.')
        if task['status']=='COMPLETED':
            fail(409,'TASK_ALREADY_COMPLETED','완료된 업무의 일정은 변경할 수 없습니다.')
        start=utc(body.planned_start_at) if body.planned_start_at else None
        due=utc(body.due_at) if body.due_at else None
        db.execute('INSERT INTO task_schedules(task_id,planned_start_at,due_at,updated_by,updated_at,reason) VALUES (?,?,?,?,?,?) '
                   'ON CONFLICT(task_id) DO UPDATE SET planned_start_at=excluded.planned_start_at,due_at=excluded.due_at,updated_by=excluded.updated_by,updated_at=excluded.updated_at,reason=excluded.reason',
                   (task_id,start,due,actor['user_id'],now(),body.reason))
        for recipient in {task['assignee_id'],task['requester_id']}-{actor['user_id']}:
            enqueue(db,case_id,recipient,'TASK_SCHEDULE_CHANGED',task_id,f'task:{task_id}:schedule:{case["version"]+1}')
        return {'task_id':task_id,'planned_start_at':start,'due_at':due,'reason':body.reason}
    return mutate(request,case_id,body,'TASK_SCHEDULE_CHANGED',operation)
