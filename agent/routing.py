import json
from typing import Any
from config import DATA_DIR


def load_routing_rules() -> dict[str, Any]:
    return json.loads((DATA_DIR / "routing_rules.json").read_text(encoding="utf-8"))


def load_school_duty_map() -> dict[str, Any]:
    path = DATA_DIR / "school_duty_map_demo.json"
    if not path.exists():
        return {"scope": "missing", "areas": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _match_duty_area(text: str, classification: dict[str, Any] | None = None) -> dict[str, Any] | None:
    duty_map = load_school_duty_map()
    haystack = " ".join([
        text or "",
        str((classification or {}).get("subcategory") or ""),
        str((classification or {}).get("dept") or ""),
        str((classification or {}).get("domain_p55") or ""),
    ])
    scored = []
    for area in duty_map.get("areas", []):
        score = sum(1 for keyword in area.get("keywords", []) if keyword and keyword in haystack)
        if score:
            scored.append((score, area))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def route_case(domain: str, *, text: str = "", classification: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = load_routing_rules()
    candidates = [x for x in rules["examples"] if x["domain"] == domain]
    base = candidates[0] if candidates else {
        "owner": "complaint_response_team",
        "action_role": None,
        "approver": "vice_principal",
        "level": "L_COOP",
        "pages": [10],
    }

    duty_map = load_school_duty_map()
    area = _match_duty_area(text, classification)

    action_role = base.get("action_role")
    approver = base.get("approver")
    collaborators: list[str] = []
    backup_role = None
    callback_needed = "UNDECIDED"
    duty_area = None
    duty_label = None

    if area:
        action_role = area.get("primary_role") or action_role
        approver = area.get("approver") or approver
        collaborators = area.get("collaborators", [])
        backup_role = area.get("backup_role")
        callback_needed = area.get("callback_default", "UNDECIDED")
        duty_area = area.get("id")
        duty_label = area.get("label")
        reason = (
            f"학교 업무분장 템플릿에서 '{duty_label}' 영역으로 매칭되었습니다. "
            "실제 학교의 해당 학년도 업무분장표에 따라 최종 담당자를 확정해야 합니다."
        )
    else:
        fallback = duty_map.get("fallback", {})
        action_role = fallback.get("primary_role") or action_role
        approver = fallback.get("approver") or approver
        backup_role = fallback.get("backup_role") or "PRINCIPAL"
        reason = fallback.get("reason") or "세부 업무영역 매칭이 없어 학교별 업무분장 확인이 필요합니다."

    owner = base.get("owner") or "complaint_response_team"
    if domain == "complex_or_sensitive":
        owner = "complaint_response_team"
        approver = "PRINCIPAL"
        backup_role = "PRINCIPAL"
        callback_needed = "NOT_REQUIRED"

    result = {
        "matched": bool(candidates),
        "suggested_owner": owner,
        "action_role": action_role,
        "collaborators": collaborators,
        "approver": approver,
        "backup_role": backup_role,
        "callback_needed": callback_needed,
        "callback_reason": (
            "생활지도 심층 여부와 관리자 대응 방향을 확인한 뒤 결정"
            if callback_needed == "UNDECIDED"
            else ("담당 부서 또는 대응팀 회신을 우선" if callback_needed == "NOT_REQUIRED" else "담임 직접 상담 필요")
        ),
        "notification_timing": "BEFORE_CLASS_IF_URGENT" if (classification or {}).get("urgency") == "HIGH" else "BREAK_OR_AFTER_SCHOOL",
        "processing_level": base.get("level"),
        "source_pages": base.get("pages", []),
        "duty_area": duty_area,
        "duty_label": duty_label,
        "duty_map_scope": duty_map.get("scope"),
        "role_labels": duty_map.get("roles", {}),
        "reason": reason,
        "requires_human_review": True,
    }
    result['recommendations'] = recommend_roles(result, text=text, classification=classification)
    return result


def recommend_roles(routing, *, text='', classification=None, evidence=()):
    """Explain duty candidates separately from retrieved procedural reference material."""
    duty_map = load_school_duty_map()
    area = next((a for a in duty_map.get('areas', []) if a['id'] == routing.get('duty_area')), None)
    matched = [k for k in (area or {}).get('keywords', []) if k in text]
    primary = routing.get('action_role') if area else 'complaint_response_team'
    candidates = [(primary, '분야 담당',
        f"{routing.get('duty_label')} 업무분장의 1차 담당입니다." if area else '일치하는 세부 분야가 없어 민원대응팀에서 담당 분야를 확인합니다.')]
    candidates += [(r, '사실확인 협조', '해당 분야 업무분장에 지정된 협조자로 필요한 사실만 확인합니다.') for r in routing.get('collaborators', [])]
    candidates += [(routing.get('approver') if area else 'HEAD_ACADEMIC_PLAN', '검토·조정', '분야 담당자의 확인 결과를 검토하고 학교 차원의 대응을 조정합니다.'),
                   (routing.get('backup_role') if area else 'PRINCIPAL', '대체·추가 지원', '업무분장에 지정된 대체 담당으로 부재나 추가 지원 필요 시 검토합니다.')]
    cls = classification or {}
    if cls.get('urgency') == 'HIGH' or cls.get('nature') in {'SAFETY', 'INFRINGEMENT_REVIEW'} or cls.get('infringement_flags'):
        candidates.insert(0, ('PRINCIPAL', '긴급·보호 검토', '긴급도 또는 안전·교육활동 보호 검토 필요성이 있어 학교 차원의 지원 판단을 우선합니다.'))
    candidates.append(('complaint_response_team', '접수·지원 조정', '민원대응팀이 분야 담당자의 처리 진행과 추가 지원 필요성을 확인합니다.'))
    results = []
    reference_purposes = {'official_manual': '민원 처리 절차와 담당자 협조 범위 확인',
        'law': '처리 권한과 법적 기준 확인', 'decree': '세부 절차와 적용 요건 확인',
        'school_policy': '학교별 운영 기준 확인', 'policy_plan': '학교 지원 방향과 정책 내용 확인'}
    references = [{**e, 'reference_reason': '접수 내용으로 검색된 자료 · ' + reference_purposes.get(e.get('source_type'), '관련 처리 기준 확인')} for e in evidence]
    for role, purpose, reason in candidates:
        if not role or any(r['role'] == role for r in results):
            continue
        results.append({'rank': len(results)+1, 'role': role, 'purpose': purpose,
            'reason': reason + (f" 원문 일치 표현: {', '.join(matched)}." if matched else ''),
            'sources': [{'source_id': duty_map.get('source_id', 'SCH-DUTY'),
                'title': '2026학년도 학교 업무분장 예시', 'source_type': 'school_duty_template',
                'file': 'data/school_duty_map_demo.json', 'section': (area or {}).get('label', '분야 미일치·담당 확인'),
                'text': ('가상 학교의 업무분장 예시이며 실제 학교의 확정 업무분장표가 아닙니다. '
                    + (f"분야 담당: {duty_map['roles'].get(area['primary_role'], area['primary_role'])} · 협조: {', '.join(duty_map['roles'].get(r,r) for r in area.get('collaborators',[])) or '별도 지정 없음'} · 검토: {duty_map['roles'].get(area['approver'], area['approver'])}" if area else '세부 분야 확인 후 담당자를 지정합니다.'))}],
            'reference_evidence': references})
        if len(results) == 3:
            break
    return results
