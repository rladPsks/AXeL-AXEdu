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
         '사건 경과와 교사의 실제 업무시간은 다릅니다. 이 화면의 시간은 기록된 활동 시간입니다.',
         '교사 순위·점수·소진 진단을 제공하지 않습니다. 교직원은 이름순으로만 표시합니다.',
         '요청·배정·원문 열람은 직접 응대로 세지 않습니다.']


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
                'cases': {'basis': '기간 안에 변경 기록이 있는 사건의 현재 상태', 'by_status': statuses},
                'tasks': {'by_type_status': task_rows},
                'support': {'requested_in_period': support_period,
                            'unacknowledged_now': len(waiting), 'unacknowledged_case_ids': limited(waiting)},
                'staff_activity': activity, 'notes': NOTES}
