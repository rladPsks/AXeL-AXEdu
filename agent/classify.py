from __future__ import annotations

import json
from typing import Any

from llm_client import LLMUnavailable, chat_json
from .schemas import TriageResult


SYSTEM_PROMPT = """당신은 학교 민원 접수·분류 보조 에이전트입니다.
최종 행정·법적 결정을 내리지 말고 분류 후보만 제안합니다.
민원 원문에 없는 사실을 추정하지 마세요.
아동학대 신고 의사 언급만으로 협박을 확정하지 마세요.
'세 번째 전화' 같은 자기보고만으로 반복민원을 확정하지 말고 DB 이력 확인 필요성을 needs_fact_check에 넣으세요.
교육활동 침해 여부, 상급기관 이관, 법적 조치는 항상 사람 검토 대상으로 남깁니다.
위험·협박 표현은 원문에서 확인되는 경우에만 후보 코드와 근거 인용을 남기세요.
"""

TRIAGE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "category": {"type": "string", "enum": ["INFO", "EDU", "SAFE", "COUNSEL", "ADMIN", "STAFF", "OTHER"]},
        "subcategory": {"type": "string"},
        "dept": {"type": "string"},
        "stage": {"type": "integer", "enum": [1, 2, 3, 4]},
        "stage_reason": {"type": "string"},
        "urgency": {"type": "string", "enum": ["HIGH", "MID", "LOW"]},
        "urgency_reason": {"type": "string"},
        "is_informational": {"type": "boolean"},
        "infringement_flags": {"type": "array", "items": {"type": "string"}},
        "infringement_evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"flag": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["flag", "quote"],
            },
        },
        "emotion": {"type": "string", "enum": ["CALM", "UPSET", "HOSTILE"]},
        "language": {"type": "string"},
        "summary_for_teacher": {"type": "string"},
        "action_for_teacher": {"type": "string"},
        "needs_fact_check": {"type": "array", "items": {"type": "string"}},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {"type": "string"},
                    "target_role": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["action", "target_role", "reason"],
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "requires_human_review": {"type": "boolean"},
        "nature": {
            "type": "string",
            "enum": ["DIRECT_RELAY", "INFO_REQUEST", "COUNSEL", "COMPLAINT", "SAFETY", "INFRINGEMENT_REVIEW"],
        },
        "legal_kind": {"type": "string", "enum": ["법정", "질의", "건의", "기타", "고충"]},
        "domain_p55": {
            "type": "string",
            "enum": ["교무/학사", "생활지도/상담", "학부모/교직원 소통", "학교 운영", "기타"],
        },
        "special_codes": {"type": "array", "items": {"type": "string"}},
        "classifier_mode": {"type": "string", "enum": ["LLM"]},
        "classifier_error": {"type": "string"},
    },
    "required": [
        "category", "subcategory", "dept", "stage", "stage_reason", "urgency", "urgency_reason",
        "is_informational", "infringement_flags", "infringement_evidence", "emotion", "language",
        "summary_for_teacher", "action_for_teacher", "needs_fact_check", "action_items", "confidence",
        "requires_human_review", "nature", "legal_kind", "domain_p55", "special_codes",
        "classifier_mode", "classifier_error"
    ],
}


def _rule_fallback(text: str, error: str = "") -> dict[str, Any]:
    if any(w in text for w in ["다쳤", "위험", "자해", "폭력", "안전", "학교폭력"]):
        category, urgency, stage, info = "SAFE", "HIGH", 2, False
        nature, domain = "SAFETY", "생활지도/상담"
    elif any(w in text for w in ["선생님", "수업", "생활지도", "차별", "혼내"]):
        category, urgency, stage, info = "EDU", "MID", 2, False
        nature, domain = "COMPLAINT", "생활지도/상담"
    elif any(w in text for w in ["언제", "몇 시", "준비물", "일정", "신청", "어디"]):
        category, urgency, stage, info = "INFO", "LOW", 1, True
        nature, domain = "INFO_REQUEST", "교무/학사"
    else:
        category, urgency, stage, info = "OTHER", "MID", 2, False
        nature, domain = "COMPLAINT", "기타"

    special_codes = []
    infringement_flags = []
    if "아동학대" in text and ("신고" in text or "고발" in text):
        special_codes.append("CHILD_ABUSE_REPORT_MENTION")
    if any(w in text for w in ["욕설", "폭언", "죽여", "가만 안", "협박"]):
        special_codes.append("VERBAL_ABUSE_REVIEW")
        infringement_flags.append("VERBAL_ABUSE_REVIEW")

    return TriageResult(
        category=category,
        subcategory="규칙 기반 예비 분류",
        dept="안전·보건" if category == "SAFE" else ("교육·학생생활" if category == "EDU" else "교육행정"),
        stage=stage,
        urgency=urgency,
        is_informational=info,
        stage_reason="LLM 미사용 또는 실패 시 규칙 기반 fallback입니다.",
        urgency_reason="본문 키워드 기반 예비 판단입니다.",
        infringement_flags=infringement_flags,
        summary_for_teacher=text[:120],
        action_for_teacher="필요한 사실관계만 확인" if category == "EDU" else "조치 불필요(관리자 처리 중)",
        confidence=0.35,
        requires_human_review=True,
        nature=nature,
        legal_kind="질의" if info else "고충",
        domain_p55=domain,
        special_codes=special_codes,
        classifier_mode="RULE_FALLBACK",
        classifier_error=error[:500],
    ).model_dump()


def classify_complaint(text: str) -> dict[str, Any]:
    try:
        payload = chat_json(
            system=SYSTEM_PROMPT,
            user=json.dumps({"complaint_text": text}, ensure_ascii=False),
            schema=TRIAGE_JSON_SCHEMA,
            schema_name="school_complaint_triage",
        )
        payload["requires_human_review"] = True
        payload["classifier_mode"] = "LLM"
        payload["classifier_error"] = ""
        return TriageResult.model_validate(payload).model_dump()
    except (LLMUnavailable, ValueError, TypeError) as exc:
        return _rule_fallback(text, error=f"{type(exc).__name__}: {exc}")
