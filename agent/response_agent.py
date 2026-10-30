from __future__ import annotations

import json
from typing import Any

from llm_client import LLMUnavailable, chat_json


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "draft": {"type": "string"},
        "basis_summary": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "claims_requiring_review": {"type": "array", "items": {"type": "string"}},
        "ready_for_human_review": {"type": "boolean"},
    },
    "required": [
        "draft",
        "basis_summary",
        "missing_information",
        "claims_requiring_review",
        "ready_for_human_review",
    ],
}

SYSTEM_PROMPT = """당신은 학교 공식 민원 답변 초안을 작성하는 에이전트입니다.
확인된 사건 사실과 제공된 근거만 사실로 단정하세요.
민원인의 주장, AI 추론, 교직원 확인 결과를 구분하세요.
법률·정책·학교 일정처럼 외부 근거가 필요한 사실은 evidence에 없으면 만들지 마세요.
일반적인 존중 표현과 문장 다듬기는 가능합니다.
미확인 잘못을 인정하거나 학교가 결정하지 않은 보상·제재·법적 조치를 약속하지 마세요.
교육활동 침해 확정, 자동 이관, 자동 제재 결론을 내리지 마세요.
최종 발송 전 사람이 검토해야 합니다.
ready_for_human_review는 "외부 발송 준비 완료"가 아니라 "사람이 검토할 수 있는 근거 있는 초안이 생성되었는지"를 뜻합니다.
확인된 사실과 미확인 사항을 구분한 초안이 생성되었다면 추가 확인 항목이 남아 있어도 true로 표시하세요.
"""


def _evidence_for_prompt(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for e in evidence[:5]:
        items.append({
            "title": e.get("title"),
            "source_id": e.get("source_id"),
            "locator": e.get("locator") or e.get("article") or e.get("pdf_page") or e.get("page"),
            "text": str(e.get("text", ""))[:1200],
        })
    return items


def generate_response_draft(
    *,
    complaint_text: str,
    confirmed_facts: list[str],
    evidence: list[dict[str, Any]],
    classification: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "complaint_text": complaint_text,
        "confirmed_facts": confirmed_facts,
        "evidence": _evidence_for_prompt(evidence),
        "classification": {
            "nature": classification.get("nature"),
            "domain_p55": classification.get("domain_p55"),
            "urgency": classification.get("urgency"),
        },
    }
    try:
        result = chat_json(
            system=SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
            schema=RESPONSE_SCHEMA,
            schema_name="school_complaint_response_draft",
        )
        if result.get("draft") and (confirmed_facts or evidence):
            result["ready_for_human_review"] = True
        return result
    except LLMUnavailable:
        if confirmed_facts:
            facts = " ".join(f"- {x}" for x in confirmed_facts)
            return {
                "draft": (
                    "안녕하세요. 문의하신 사항을 학교에서 확인하고 있습니다. "
                    "현재 확인된 내용을 바탕으로 담당자가 최종 검토 후 안내드리겠습니다.\n"
                    f"확인된 내용: {facts}"
                ),
                "basis_summary": confirmed_facts,
                "missing_information": [],
                "claims_requiring_review": [],
                "ready_for_human_review": True,
            }
        return {
            "draft": "문의 내용을 확인 중입니다. 필요한 사실 확인 후 담당자가 안내드리겠습니다.",
            "basis_summary": [],
            "missing_information": ["사건 관련 확인 결과"],
            "claims_requiring_review": [],
            "ready_for_human_review": False,
        }
