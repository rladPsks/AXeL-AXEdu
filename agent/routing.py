import json
from typing import Any
from config import DATA_DIR


def load_routing_rules() -> dict[str, Any]:
    return json.loads((DATA_DIR / "routing_rules.json").read_text(encoding="utf-8"))


def route_case(domain: str) -> dict[str, Any]:
    rules = load_routing_rules()
    candidates = [x for x in rules["examples"] if x["domain"] == domain]
    if not candidates:
        return {"matched": False, "suggested_owner": "complaint_response_team", "action_role": None,
                "approver": "vice_principal", "reason": "학교별 업무분장 확인이 필요합니다.", "requires_human_review": True}
    item = candidates[0]
    return {"matched": True, "suggested_owner": item["owner"], "action_role": item["action_role"],
            "approver": item["approver"], "processing_level": item["level"], "source_pages": item["pages"],
            "reason": "매뉴얼의 담당자 지정 예시를 참고한 역할 후보입니다. 실제 담당자는 학교 업무분장표 확인이 필요합니다.",
            "requires_human_review": True}
