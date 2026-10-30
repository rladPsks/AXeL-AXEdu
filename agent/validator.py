from __future__ import annotations

import re
from typing import Any


PROMISE_PATTERNS = (
    "전적으로 학교의 잘못",
    "학교의 책임을 인정",
    "반드시 보상",
    "무조건 조치",
    "반드시 처벌",
    "처벌하겠습니다",
)

RISKY_CONTACT_TERMS = ("전화 상담", "전화드리", "방문 상담", "방문해", "면담하러")


def validate_response(
    *,
    draft: str,
    evidence: list[dict[str, Any]],
    classification: dict[str, Any],
    response_generation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    text = str(draft or "")
    response_generation = response_generation or {}

    for phrase in PROMISE_PATTERNS:
        if phrase in text:
            issues.append({
                "code": "UNAUTHORIZED_PROMISE",
                "message": f"학교가 확정하지 않은 책임 인정·약속 표현을 검토하세요: {phrase}",
            })

    legal_reference = bool(re.search(r"제\s*\d+\s*조|법률|시행령|법에 따라", text))
    if legal_reference and not evidence:
        issues.append({
            "code": "UNGROUNDED_POLICY_CLAIM",
            "message": "법령·규정 표현이 있으나 연결된 공식 근거가 없습니다.",
        })

    risk_signal = bool(
        classification.get("urgency") == "HIGH"
        or classification.get("infringement_flags")
        or set(classification.get("special_codes") or []).intersection({
            "VERBAL_ABUSE_REVIEW", "THREAT_REVIEW", "SAFETY_RISK"
        })
    )
    if risk_signal and any(term in text for term in RISKY_CONTACT_TERMS):
        issues.append({
            "code": "RISKY_DIRECT_CONTACT",
            "message": "위험·침해 검토 민원에서 교직원의 직접 전화·방문 응대를 자동 권유하지 마세요.",
        })

    for claim in response_generation.get("claims_requiring_review") or []:
        issues.append({
            "code": "HUMAN_REVIEW_CLAIM",
            "message": str(claim),
        })

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "auto_send_allowed": False,
        "human_review_required": True,
    }
