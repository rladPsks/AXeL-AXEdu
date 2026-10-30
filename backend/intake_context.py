"""Read intake context without bypassing cross-case access or version checks."""
import json

from .access import DomainError, accessible_case, fail


def history_access(db, actor, entry):
    case = accessible_case(db, actor, entry['case_id'])
    if entry.get('case_version') != case['version']:
        fail(409, 'INPUT_VERSION_CONFLICT', '관련 사건 이력이 변경되었습니다. 입력을 다시 확인하세요.')


def intake_context(db, actor, row):
    item = dict(row)
    item['related_people'] = json.loads(item['related_people'])
    for name in ('classification', 'routing', 'workflow'):
        raw = item.pop(name + '_json', None)
        item[name] = json.loads(raw) if raw else None
    workflow = item.get('workflow') or {}
    tools = workflow.get('tools') or {}
    visible = []
    for entry in tools.get('history', []):
        try:
            history_access(db, actor, entry)
        except DomainError:
            continue
        visible.append(entry)
    if 'history' in tools:
        tools['history'] = visible
    return item
