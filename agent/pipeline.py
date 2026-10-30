from typing import Any
from .classify import classify_complaint
from .draft import draft_information_reply, teacher_card
from .knowledge import retrieve
from .rules import apply_rules
from .routing import route_case


def process(complaint: dict[str, Any], history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    text = str(complaint.get("text", "")).strip()
    if not text:
        raise ValueError("민원 내용이 비어 있습니다.")
    cls = apply_rules(classify_complaint(text), history or [])
    domain = ("simple_inquiry" if cls["is_informational"] else
              "student_counseling" if cls["category"] in {"EDU", "COUNSEL"} else
              "complex_or_sensitive" if cls["stage"] == 4 else "fact_check")
    routing = route_case(domain)
    evidence = retrieve(text)
    reply = draft_information_reply(text, evidence) if cls["is_informational"] else (
        "추가 사실 확인과 담당자 검토가 필요한 사안입니다. 자동 발송하지 말고 관리자 승인 후 처리하세요.")
    risk = bool(cls.get("infringement_flags"))
    return {"classification": cls, "routing": routing, "evidence": evidence,
            "response_draft": reply, "teacher_card": teacher_card(cls["summary_for_teacher"], cls["action_for_teacher"], risk),
            "escalation_status": cls.get("escalation_status", "NOT_PROPOSED"), "requires_human_review": True}
