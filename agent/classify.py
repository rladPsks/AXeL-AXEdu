from __future__ import annotations

import json
from typing import Any

from llm_client import LLMUnavailable, chat_json
from .schemas import TriageResult


SYSTEM_PROMPT = """당신은 학교 민원 접수·분류 보조 에이전트입니다.
최종 행정·법적 결정을 내리지 말고 분류 후보만 제안합니다.
반드시 사용자의 원문에서 확인되는 내용만 근거로 사용하세요.
아동학대 신고 의사 언급만으로 협박을 확정하지 마세요.
교육활동 침해 여부, 상급기관 이관, 법적 조치는 항상 사람 검토 대상으로 남깁니다.

다음 JSON 필드를 반환하세요:
category, subcategory, dept, stage, stage_reason, urgency, urgency_reason,
is_informational, infringement_flags, infringement_evidence, emotion, language,
summary_for_teacher, action_for_teacher, needs_fact_check, action_items, confidence,
requires_human_review, nature, legal_kind, domain_p55, special_codes, classifier_mode.
classifier_mode은 반드시 LLM으로 설정하세요.
"""


def _rule_fallback(text: str) -> dict[str, Any]:
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

    result = TriageResult(
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
    )
    return result.model_dump()


def classify_complaint(text: str) -> dict[str, Any]:
    try:
        payload = chat_json(
            system=SYSTEM_PROMPT,
            user=json.dumps({"complaint_text": text}, ensure_ascii=False),
        )
        payload["requires_human_review"] = True
        payload["classifier_mode"] = "LLM"
        result = TriageResult.model_validate(payload)
        return result.model_dump()
    except (LLMUnavailable, ValueError, TypeError):
        return _rule_fallback(text)
