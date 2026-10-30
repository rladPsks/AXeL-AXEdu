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
    duty_area = None
    duty_label = None

    if area:
        action_role = area.get("primary_role") or action_role
        approver = area.get("approver") or approver
        collaborators = area.get("collaborators", [])
        duty_area = area.get("id")
        duty_label = area.get("label")
        reason = (
            f"학교 업무분장 템플릿에서 '{duty_label}' 영역으로 매칭되었습니다. "
            "실제 학교의 해당 학년도 업무분장표에 따라 최종 담당자를 확정해야 합니다."
        )
    else:
        reason = "세부 업무영역 매칭이 없어 학교별 업무분장 확인이 필요합니다."

    owner = base.get("owner") or "complaint_response_team"
    if domain == "complex_or_sensitive":
        owner = "principal"
        approver = "principal"

    return {
        "matched": bool(candidates),
        "suggested_owner": owner,
        "action_role": action_role,
        "collaborators": collaborators,
        "approver": approver,
        "processing_level": base.get("level"),
        "source_pages": base.get("pages", []),
        "duty_area": duty_area,
        "duty_label": duty_label,
        "duty_map_scope": duty_map.get("scope"),
        "reason": reason,
        "requires_human_review": True,
    }
