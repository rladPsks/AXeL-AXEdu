"""Durable in-app inbox only. No email, SMS or external messaging is sent."""
import argparse
import time
from datetime import datetime, timedelta
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from .access import DomainError, accessible_case, admin, authenticate, fail, participate
from .commands import command_identity, replay_command, save_command
from .coordination import policy, resolve_support, utc
from .db import Database, audit, now, uid

router=APIRouter()


class EmptyCommand(BaseModel):
    model_config=ConfigDict(extra='forbid')


def notification_event(db,notification_id,status,actor):
    db.execute('INSERT INTO notification_events(id,notification_id,status,actor_id,created_at) VALUES (?,?,?,?,?)',
               (uid(),notification_id,status,actor,now()))


def enqueue(db,case_id,recipient_id,kind,resource_id,dedupe_key,severity='NORMAL',at=None):
    case=db.execute('SELECT school_id FROM cases WHERE id=?',(case_id,)).fetchone()
    if severity!='URGENT' and not policy(db,case['school_id'])['alerts_enabled']:
        return None
    notification_id=uid()
    stamp=at or now()
    cursor=db.execute('INSERT OR IGNORE INTO inbox_notifications(id,school_id,case_id,recipient_id,kind,resource_id,severity,dedupe_key,next_attempt_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                      (notification_id,case['school_id'],case_id,recipient_id,kind,resource_id,severity,dedupe_key,stamp,stamp))
    if cursor.rowcount:
        notification_event(db,notification_id,'QUEUED','system:inbox')
        return notification_id
    return None


def scan_reminders(db,at):
    moment=datetime.fromisoformat(at)
    for task in db.execute("SELECT t.*,s.due_at,c.school_id FROM tasks t JOIN task_schedules s ON s.task_id=t.id "
                           "JOIN cases c ON c.id=t.case_id WHERE t.status!='COMPLETED' AND c.status='OPEN' AND s.due_at IS NOT NULL").fetchall():
        config=policy(db,task['school_id'])
        if moment>=datetime.fromisoformat(task['due_at'])+timedelta(minutes=config['overdue_grace_minutes']):
            for recipient in {task['assignee_id'],task['requester_id']}:
                enqueue(db,task['case_id'],recipient,'TASK_OVERDUE',task['id'],f'task:{task["id"]}:overdue:{task["due_at"]}',at=at)
    for support in db.execute("SELECT s.*,c.school_id,c.version,c.owner_id FROM support_requests s JOIN cases c ON c.id=s.case_id "
                              "WHERE s.status='REQUESTED' AND c.status='OPEN'").fetchall():
        config=policy(db,support['school_id'])
        timed_out=moment>=datetime.fromisoformat(support['assigned_at'] or support['created_at'])+timedelta(minutes=config['support_ack_minutes'])
        available,availability=resolve_support(db,support['school_id'],support['coordinator_id'],at)
        if availability=='NO_AVAILABLE_SUBSTITUTE':
            for contact in {support['requester_id'],support['owner_id']}:
                enqueue(db,support['case_id'],contact,'SUPPORT_SUBSTITUTE_UNAVAILABLE',support['id'],f'support:{support["id"]}:substitute-unavailable',severity='URGENT' if support['type']=='URGENT' else 'NORMAL',at=at)
        if available!=support['coordinator_id'] and availability=='SUBSTITUTE':
            recipient,routing=available,'ABSENCE_SUBSTITUTE'
        elif not timed_out:
            continue
        else:
            recipient,routing=resolve_support(db,support['school_id'],support['coordinator_id'],at,exclude={support['coordinator_id']})
        if recipient!=support['coordinator_id'] and routing!='NO_AVAILABLE_SUBSTITUTE':
            db.execute('UPDATE support_requests SET coordinator_id=?,routing_reason=?,assigned_at=? WHERE id=?',
                       (recipient,routing if routing=='ABSENCE_SUBSTITUTE' else 'UNACKNOWLEDGED_SUBSTITUTE',at,support['id']))
            participate(db,support['case_id'],recipient)
            case=db.execute('SELECT version FROM cases WHERE id=?',(support['case_id'],)).fetchone()
            version=case['version']+1
            db.execute('UPDATE cases SET version=? WHERE id=?',(version,support['case_id']))
            audit(db,{'user_id':'system:inbox'},support['case_id'],'SUPPORT_REROUTED',version,
                  {'support_request_id':support['id'],'from_coordinator_id':support['coordinator_id'],'coordinator_id':recipient})
            enqueue(db,support['case_id'],recipient,'SUPPORT_REROUTED',support['id'],f'support:{support["id"]}:rerouted:{recipient}',severity='URGENT' if support['type']=='URGENT' else 'NORMAL',at=at)
            for contact in {support['requester_id'],support['owner_id']}-{recipient}:
                enqueue(db,support['case_id'],contact,'SUPPORT_COORDINATOR_CHANGED',support['id'],f'support:{support["id"]}:coordinator:{recipient}',severity='URGENT' if support['type']=='URGENT' else 'NORMAL',at=at)
        if timed_out:
            for contact in {recipient,support['owner_id']}:
                enqueue(db,support['case_id'],contact,'SUPPORT_UNCONFIRMED',support['id'],f'support:{support["id"]}:unconfirmed',
                        severity='URGENT' if support['type']=='URGENT' else 'NORMAL',at=at)


def dispatch_once(database,at=None):
    at=at or now()
    with database.transaction() as db:
        scan_reminders(db,at)
        rows=db.execute("SELECT * FROM inbox_notifications WHERE status='QUEUED' AND next_attempt_at<=? ORDER BY (severity='URGENT') DESC,created_at,id LIMIT 100",(at,)).fetchall()
        for row in rows:
            actor=db.execute('SELECT * FROM memberships WHERE user_id=? AND school_id=? AND active=1',
                             (row['recipient_id'],row['school_id'])).fetchone()
            error=None
            if actor is None:
                error='RECIPIENT_UNAVAILABLE'
            else:
                try:
                    accessible_case(db,actor,row['case_id'])
                except DomainError:
                    error='CASE_ACCESS_REVOKED'
            attempts=row['attempts']+1
            if error:
                status='FAILED' if attempts>=row['max_attempts'] or error=='CASE_ACCESS_REVOKED' else 'QUEUED'
                next_at=utc(datetime.fromisoformat(at)+timedelta(seconds=2**attempts))
                db.execute('UPDATE inbox_notifications SET status=?,attempts=?,error_code=?,next_attempt_at=? WHERE id=?',
                           (status,attempts,error,next_at,row['id']))
            else:
                status='DELIVERED'
                db.execute("UPDATE inbox_notifications SET status='DELIVERED',attempts=?,error_code=NULL,delivered_at=? WHERE id=?",(attempts,at,row['id']))
            notification_event(db,row['id'],status,'system:inbox')
        return len(rows)


@router.get('/api/notifications')
def inbox(request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        return [dict(r) for r in db.execute("SELECT n.id,n.case_id,c.title AS case_title,n.kind,n.resource_id,n.severity,n.status,n.created_at,n.delivered_at,n.acknowledged_at "
                "FROM inbox_notifications n JOIN cases c ON c.id=n.case_id AND c.school_id=n.school_id "
                "WHERE n.school_id=? AND n.recipient_id=? AND n.status IN('DELIVERED','ACKNOWLEDGED') "
                "AND (?='ADMIN' OR EXISTS(SELECT 1 FROM case_participants p WHERE p.case_id=c.id AND p.user_id=?)) ORDER BY (n.status='ACKNOWLEDGED'),n.created_at DESC,n.id DESC LIMIT 100",
                (actor['school_id'],actor['user_id'],actor['role'],actor['user_id']))]


def notification_command(notification_id,body,request,retry=False):
    identity=command_identity(request,body)
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        if retry:
            admin(actor)
        row=db.execute('SELECT * FROM inbox_notifications WHERE id=? AND school_id=?',(notification_id,actor['school_id'])).fetchone()
        if row is None or (not retry and row['recipient_id']!=actor['user_id']):
            fail(404,'NOTIFICATION_NOT_FOUND','알림을 찾을 수 없습니다.')
        accessible_case(db,actor,row['case_id'])
        replay=replay_command(db,actor,identity)
        if replay is not None:
            return replay
        if retry:
            if row['status']!='FAILED':
                fail(409,'INVALID_TRANSITION','전달 실패 알림만 다시 시도할 수 있습니다.')
            db.execute("UPDATE inbox_notifications SET status='QUEUED',max_attempts=attempts+3,next_attempt_at=?,error_code=NULL WHERE id=?",(now(),notification_id))
            status='QUEUED'
        else:
            if row['status'] not in {'DELIVERED','ACKNOWLEDGED'}:
                fail(409,'NOTIFICATION_NOT_DELIVERED','수신함에 전달된 알림만 확인할 수 있습니다.')
            status='ACKNOWLEDGED'
            if row['status']!='ACKNOWLEDGED':
                db.execute("UPDATE inbox_notifications SET status='ACKNOWLEDGED',acknowledged_at=? WHERE id=?",(now(),notification_id))
        notification_event(db,notification_id,status,actor['user_id'])
        response={'notification_id':notification_id,'status':status}
        save_command(db,actor,identity,response)
        return JSONResponse(response)


@router.post('/api/notifications/{notification_id}/acknowledge')
def acknowledge(notification_id:str,body:EmptyCommand,request:Request):
    return notification_command(notification_id,body,request)


@router.post('/api/notifications/{notification_id}/retry')
def retry(notification_id:str,body:EmptyCommand,request:Request):
    return notification_command(notification_id,body,request,retry=True)


@router.get('/api/school/notification-status')
def notification_status(request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        return [dict(r) for r in db.execute('SELECT id,case_id,recipient_id,kind,severity,status,attempts,error_code,created_at FROM inbox_notifications WHERE school_id=? ORDER BY created_at DESC,id DESC LIMIT 100',(actor['school_id'],))]


if __name__=='__main__':
    import os
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',default=os.getenv('SCHOOL_AGENT_DB','data/private/dev.sqlite3'))
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    database=Database(args.db)
    while True:
        dispatch_once(database)
        if args.once:
            break
        time.sleep(2)
