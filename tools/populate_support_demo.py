"""Add labelled support demo fixtures via authenticated APIs without deploying code."""
import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.seed_dashboard import SUPPORT_SAMPLES, SUPPORT_TASKS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='https://axel-axedu-demo.onrender.com')
    args = parser.parse_args()
    token = None

    def call(path, body=None, key=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if key:
            headers['Idempotency-Key'] = key
        request = urllib.request.Request(args.base.rstrip('/') + path,
            data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
            headers=headers)
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)

    # Both routes reject ordinary, unmarked institutional databases.
    accounts = {a['id'] for a in call('/api/demo/accounts')}
    required = {s[0] for s in SUPPORT_SAMPLES}
    if not required <= accounts:
        raise RuntimeError('Required fictional support accounts are unavailable')
    token = call('/api/demo/login', {'account': 'admin'})['token']
    cases = {}
    # Preflight every target before making any changes.
    for number in {s[1] for s in SUPPORT_SAMPLES}:
        cid = f'demo-pattern-{number:02d}'
        case = call(f'/api/cases/{cid}')
        if case['school_id'] != 'demo-school' or not case['title'].startswith('[반복 시연]'):
            raise RuntimeError('Expected fictional case missing: ' + cid)
        cases[number] = cid

    for index, (staff, number, kind, duration, note) in enumerate(SUPPORT_SAMPLES):
        cid = cases[number]
        marker = f'[가상 시연·지원-{index:02d}]'
        logs = call(f'/api/cases/{cid}/activities')
        if any((row.get('note') or '').startswith(marker) or
               row['id'] == f'demo-support-activity-{index:02d}' for row in logs):
            continue
        version = call(f'/api/cases/{cid}')['version']
        call(f'/api/cases/{cid}/activities', {
            'expected_version': version, 'staff_id': staff, 'kind': kind,
            'occurred_at': (datetime.now(timezone.utc)-timedelta(hours=index+1)).isoformat(),
            'duration_seconds': duration, 'note': marker+' '+note+' · 실제 활동 기록 아님.'
        }, f'support-demo-activity-v1-{index}')

    for index, (staff, number, kind, question) in enumerate(SUPPORT_TASKS):
        cid = cases[number]
        case = call(f'/api/cases/{cid}')
        marker = f'[가상 시연·지원업무-{index:02d}]'
        if any(t['question'].startswith(marker) or t['id'] == f'demo-support-task-{index:02d}'
               for t in case['tasks']):
            continue
        call(f'/api/cases/{cid}/tasks', {
            'expected_version': case['version'], 'type': kind, 'assignee_id': staff,
            'question': marker+' '+question, 'callback_needed': 'NOT_REQUIRED'
        }, f'support-demo-task-v1-{index}')

    rows = {s['staff_id']: s for s in call('/api/dashboard')['staff_detail']}
    assert required <= rows.keys()
    assert all(rows[s]['entries'] > 0 and rows[s]['pending_tasks_now'] > 0 for s in required)
    print(json.dumps({'verified_support_staff': [
        {k: rows[s][k] for k in ('staff_id', 'entries', 'recorded_seconds', 'pending_tasks_now')}
        for s in sorted(required)]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
