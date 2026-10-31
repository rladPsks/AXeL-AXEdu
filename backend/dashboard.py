"""School-scoped support dashboard. Aggregates recorded data only; never ranks or scores staff."""
import json
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Query, Request

from .access import admin, authenticate, fail

router = APIRouter()
# Korea has no daylight saving time; a fixed offset avoids depending on a system tz database.
KST = timezone(timedelta(hours=9), 'Asia/Seoul')
CASE_LIMIT = 20
NOTES = ['기록된 활동만 집계합니다. 기록하지 않은 시간은 0분이 아니라 미기록입니다.',
         '민원 경과와 교사의 실제 업무시간은 다릅니다. 이 화면의 시간은 기록된 활동 시간입니다.']


def period_bounds(start, end):
    today = datetime.now(KST).date()
    try:
        last = date.fromisoformat(end) if end else today
        first = date.fromisoformat(start) if start else last - timedelta(days=29)
    except ValueError:
        fail(422, 'INVALID_PERIOD', '기간은 YYYY-MM-DD 형식으로 입력하세요.')
    if first > last or (last - first).days > 366:
        fail(422, 'INVALID_PERIOD', '시작일은 종료일보다 늦을 수 없고 기간은 367일 이내여야 합니다.')
    # KST calendar days -> half-open UTC range, so late-evening KST records stay on their own day.
    lower = datetime.combine(first, time.min, tzinfo=KST).astimezone(timezone.utc).isoformat()
    upper = datetime.combine(last + timedelta(days=1), time.min, tzinfo=KST).astimezone(timezone.utc).isoformat()
    return first, last, lower, upper


def limited(ids):
    unique = sorted(set(ids))
    return unique[:CASE_LIMIT]


@router.get('/api/dashboard')
def dashboard(request: Request, start: str = Query('', alias='from'), end: str = Query('', alias='to')):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        admin(actor)
        school = actor['school_id']
        first, last, lower, upper = period_bounds(start, end)

        statuses = {'OPEN': 0, 'CLOSED': 0}
        for row in db.execute(
                'SELECT c.status AS status, COUNT(DISTINCT c.id) AS n FROM cases c JOIN audit_events a ON a.case_id=c.id '
                'WHERE c.school_id=? AND a.created_at>=? AND a.created_at<? GROUP BY c.status', (school, lower, upper)):
            statuses[row['status']] = row['n']

        tasks = {}
        for row in db.execute(
                'SELECT t.type AS type, t.status AS status, t.case_id AS case_id FROM tasks t JOIN cases c ON c.id=t.case_id '
                'WHERE c.school_id=? AND t.created_at>=? AND t.created_at<?', (school, lower, upper)):
            item = tasks.setdefault((row['type'], row['status']), [])
            item.append(row['case_id'])
        task_rows = [{'type': kind, 'status': status, 'count': len(ids), 'case_ids': limited(ids)}
                     for (kind, status), ids in sorted(tasks.items())]

        support_period = {}
        for row in db.execute(
                'SELECT s.status AS status, COUNT(*) AS n FROM support_requests s JOIN cases c ON c.id=s.case_id '
                'WHERE c.school_id=? AND s.created_at>=? AND s.created_at<? GROUP BY s.status', (school, lower, upper)):
            support_period[row['status']] = row['n']
        waiting = [r['case_id'] for r in db.execute(
            "SELECT s.case_id AS case_id FROM support_requests s JOIN cases c ON c.id=s.case_id "
            "WHERE c.school_id=? AND s.status='REQUESTED' ORDER BY s.created_at", (school,))]

        staff = {}
        for row in db.execute(
                'SELECT staff_id,kind,duration_seconds,case_id FROM activity_logs '
                'WHERE school_id=? AND occurred_at>=? AND occurred_at<?', (school, lower, upper)):
            item = staff.setdefault(row['staff_id'], {'by_kind': {}, 'recorded_seconds': 0, 'entries': 0,
                                                     'entries_without_duration': 0, 'cases': []})
            item['by_kind'][row['kind']] = item['by_kind'].get(row['kind'], 0) + 1
            item['entries'] += 1
            item['cases'].append(row['case_id'])
            if row['duration_seconds'] is None:
                item['entries_without_duration'] += 1
            else:
                item['recorded_seconds'] += row['duration_seconds']
        activity = [{'staff_id': staff_id, 'by_kind': dict(sorted(v['by_kind'].items())),
                     'recorded_seconds': v['recorded_seconds'], 'entries': v['entries'],
                     'entries_without_duration': v['entries_without_duration'], 'case_ids': limited(v['cases'])}
                    for staff_id, v in sorted(staff.items())]

        return {'period': {'from': first.isoformat(), 'to': last.isoformat(), 'timezone': 'Asia/Seoul'},
                'cases': {'basis': '기간 안에 변경 기록이 있는 민원의 현재 상태', 'by_status': statuses},
                'tasks': {'by_type_status': task_rows},
                'support': {'requested_in_period': support_period,
                            'unacknowledged_now': len(waiting), 'unacknowledged_case_ids': limited(waiting)},
                'staff_activity': activity, 'staff_detail': staff_details(db,school,lower,upper), 'notes': NOTES}


def staff_details(db,school,lower,upper):
    """Separate period exposure/activity from the current queue. No inferred work time."""
    from collections import defaultdict
    cases={r['id']:dict(r) for r in db.execute('SELECT c.id,c.title,c.status,i.received_at,i.classification_json FROM cases c LEFT JOIN case_intakes i ON i.case_id=c.id WHERE c.school_id=?',(school,))}
    tasks=[dict(r) for r in db.execute('SELECT t.* FROM tasks t JOIN cases c ON c.id=t.case_id WHERE c.school_id=?',(school,))]
    activities=[dict(r) for r in db.execute('SELECT * FROM activity_logs WHERE school_id=? AND occurred_at>=? AND occurred_at<?',(school,lower,upper))]
    members=[dict(r) for r in db.execute('SELECT user_id,role FROM memberships WHERE school_id=? AND active=1 ORDER BY user_id',(school,))]
    participants=defaultdict(set)
    for r in db.execute('SELECT p.* FROM case_participants p JOIN cases c ON c.id=p.case_id WHERE c.school_id=?',(school,)):
        participants[r['user_id']].add(r['case_id'])
    lower_dt=datetime.fromisoformat(lower);upper_dt=datetime.fromisoformat(upper)
    clock=datetime.now(timezone.utc)
    def instant(value):
        if not value: return None
        try: return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
        except ValueError: return None
    def within(value):
        at=instant(value)
        return at is not None and lower_dt<=at<upper_dt
    result=[]
    for member in members:
        identity=member['user_id']
        logs=[a for a in activities if a['staff_id']==identity]
        mine=[t for t in tasks if t['assignee_id']==identity]
        period_tasks=[t for t in mine if within(t['created_at'])]
        pending=[t for t in mine if t['status']!='COMPLETED' and cases[t['case_id']]['status']!='CLOSED']
        case_ids={a['case_id'] for a in logs}|{t['case_id'] for t in period_tasks}|{cid for cid in participants[identity] if within(cases[cid]['received_at'])}
        rows=[];daily={};by_kind={}
        for a in logs:
            day=instant(a['occurred_at']).astimezone(KST).date().isoformat()
            d=daily.setdefault(day,{'date':day,'entries':0,'contact_count':0,'recorded_seconds':0,'missing_duration':0})
            k=by_kind.setdefault(a['kind'],{'kind':a['kind'],'entries':0,'recorded_seconds':0,'missing_duration':0})
            for group in (d,k):
                group['entries']+=1
                if a['duration_seconds'] is None: group['missing_duration']+=1
                else: group['recorded_seconds']+=a['duration_seconds']
            if a['kind'] in ('DIRECT_CONTACT','CALLBACK','COUNSEL'): d['contact_count']+=1
        for cid in sorted(case_ids|{t['case_id'] for t in pending}):
            case=cases[cid];cls=json.loads(case['classification_json'] or '{}')
            case_logs=[a for a in logs if a['case_id']==cid]
            durations=[a['duration_seconds'] for a in case_logs if a['duration_seconds'] is not None]
            waiting=[t for t in pending if t['case_id']==cid]
            waits=[max(0,(clock-instant(t['created_at'])).total_seconds()) for t in waiting if instant(t['created_at'])]
            rows.append({'case_id':cid,'title':case['title'],'status':case['status'],'in_period':cid in case_ids,'nature':cls.get('nature') or 'UNCLASSIFIED','urgency':cls.get('urgency') or 'UNCLASSIFIED','infringement_concern':bool(cls.get('infringement_flags')),'entries':len(case_logs),'recorded_seconds':sum(durations) if durations else None,'missing_duration':sum(a['duration_seconds'] is None for a in case_logs),'pending_tasks':len(waiting),'oldest_wait_seconds':max(waits,default=None)})
        recorded=[a['duration_seconds'] for a in logs if a['duration_seconds'] is not None]
        measured_cases={a['case_id'] for a in logs if a['duration_seconds'] is not None}
        result.append({'staff_id':identity,'role':member['role'],'linked_cases':len(case_ids),'open_cases':sum(cases[c]['status']=='OPEN' for c in case_ids),'high_urgency_cases':sum(r['urgency']=='HIGH' and r['in_period'] for r in rows),'contact_count':sum(a['kind'] in ('DIRECT_CONTACT','CALLBACK','COUNSEL') for a in logs),'entries':len(logs),'recorded_seconds':sum(recorded) if recorded else None,'missing_duration':len(logs)-len(recorded),'recording_coverage':round(len(recorded)/len(logs)*100) if logs else None,'average_recorded_case_seconds':sum(recorded)/len(measured_cases) if measured_cases else None,'pending_tasks_now':len(pending),'oldest_wait_seconds':max((r['oldest_wait_seconds'] for r in rows if r['oldest_wait_seconds'] is not None),default=None),'by_kind':list(by_kind.values()),'daily':sorted(daily.values(),key=lambda d:d['date']),'cases':rows})
    return result
