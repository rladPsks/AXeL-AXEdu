from typing import Any
from .classify import classify_complaint
from .draft import draft_information_reply, teacher_card
from .knowledge import retrieve
from .rules import apply_rules
from .routing import route_case


def _routing_domain(cls: dict[str, Any]) -> str:
    if cls.get("nature") == "INFO_REQUEST" or cls.get("is_informational"):
        return "simple_inquiry"
    if cls.get("nature") == "COUNSEL" or cls.get("domain_p55") == "생활지도/상담":
        return "student_counseling"
    if cls.get("nature") in {"SAFETY", "INFRINGEMENT_REVIEW"} or cls.get("stage") == 4:
        return "complex_or_sensitive"
    return "fact_check"


def _allowed_source_types(cls: dict[str, Any], text: str) -> set[str] | None:
    if cls.get("nature") != "INFO_REQUEST":
        return None
    policy_terms = (
        "법", "법률", "교육활동 침해", "교권", "교육청", "교육지원청",
        "매뉴얼", "정책", "절차", "조치", "신고", "보호조치",
    )
    if any(term in text for term in policy_terms):
        return {"law", "decree", "official_manual", "local_rule", "policy_plan"}
    return {"school_policy"}


def process(complaint: dict[str, Any], history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    text = str(complaint.get("text", "")).strip()
    if not text:
        raise ValueError("민원 내용이 비어 있습니다.")

    cls = apply_rules(classify_complaint(text), history or [])
    routing = route_case(_routing_domain(cls), text=text, classification=cls)
    allowed_source_types = _allowed_source_types(cls, text)
    evidence = retrieve(
        text,
        as_of_date=complaint.get("as_of_date"),
        jurisdiction=complaint.get("jurisdiction"),
        allowed_source_types=allowed_source_types,
    )
    reply = draft_information_reply(text, evidence) if cls["is_informational"] else (
        "추가 사실 확인과 담당자 검토가 필요한 사안입니다. 자동 발송하지 말고 관리자 승인 후 처리하세요."
    )
    risk = bool(cls.get("infringement_flags") or cls.get("special_codes"))

    return {
        "classification": cls,
        "routing": routing,
        "evidence": evidence,
        "response_draft": reply,
        "teacher_card": teacher_card(cls["summary_for_teacher"], cls["action_for_teacher"], risk),
        "escalation_status": cls.get("escalation_status", "NOT_PROPOSED"),
        "requires_human_review": True,
    }
