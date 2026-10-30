from __future__ import annotations

from typing import Any


def decide_actions(classification: dict[str, Any], routing: dict[str, Any], evidence: list[dict]) -> list[dict[str, Any]]:
    """분류 결과를 실제 학교 업무 단위로 변환한다.

    최종 법적 판단·제재·외부 이관은 생성하지 않는다. 이 함수는
    학교 내부 업무와 검토 요청만 만든다.
    """
    actions: list[dict[str, Any]] = []
    nature = classification.get("nature")
    domain = classification.get("domain_p55")
    urgency = classification.get("urgency")
    special_codes = set(classification.get("special_codes") or [])
    infringement_flags = set(classification.get("infringement_flags") or [])

    handling_route = classification.get("handling_route")

    if nature == "INFO_REQUEST" and handling_route == "FRONT_DESK_RESOLVE":
        if evidence:
            actions.append({
                "task_type": "RESPONSE_REVIEW",
                "assignee_role": routing.get("action_role") or routing.get("suggested_owner") or "complaint_response_team",
                "reason": "학교 자료 근거가 검색되어 권한 범위 내 답변 검토가 필요합니다.",
                "instructions": ["검색 근거가 질문을 실제로 뒷받침하는지 확인", "확인 후 보호자 회신"],
            })
        else:
            actions.append({
                "task_type": "FACT_CHECK",
                "assignee_role": routing.get("action_role") or "school_information_owner",
                "reason": "현재 연결된 자료만으로 확정하기 어려워 업무분장 담당자의 사실 확인이 필요합니다.",
                "instructions": ["학교 공지·학사일정·담당 부서에서 사실 확인", "확인된 내용과 출처를 민원에 회신"],
            })
    elif nature == "INFO_REQUEST" and handling_route == "STAFF_OR_TEAM":
        actions.append({
            "task_type": "FACT_CHECK",
            "assignee_role": routing.get("action_role") or "relevant_staff",
            "reason": "정보 요청 형태이지만 학교 내부 사실 확인이 필요한 사안입니다.",
            "instructions": classification.get("needs_fact_check") or ["관련 사실과 맥락 확인"],
        })
    elif nature == "COUNSEL":
        actions.append({
            "task_type": "STUDENT_COUNSEL",
            "assignee_role": routing.get("action_role") or "homeroom_teacher",
            "reason": "학생 맥락을 아는 교직원의 상담·확인이 필요한 사안입니다.",
            "instructions": ["상담 목적과 쟁점을 확인", "업무상 필요한 최소 결과만 기록"],
        })
    elif nature in {"SAFETY", "INFRINGEMENT_REVIEW"}:
        actions.append({
            "task_type": "ADMIN_REVIEW",
            "assignee_role": routing.get("approver") or "vice_principal",
            "reason": "안전 또는 교육활동 보호 관련 검토가 필요한 사안입니다.",
            "instructions": ["원문 근거 구간 확인", "즉시 필요한 학교 지원 여부 판단"],
        })
    elif domain == "생활지도/상담":
        actions.append({
            "task_type": "FACT_CHECK",
            "assignee_role": routing.get("action_role") or "homeroom_teacher",
            "reason": "생활지도 관련 사실관계와 학생 맥락 확인이 필요합니다.",
            "instructions": classification.get("needs_fact_check") or [
                "발생 시점과 상황 확인",
                "지도 사유와 관련 맥락 확인",
            ],
        })
    else:
        actions.append({
            "task_type": "FACT_CHECK",
            "assignee_role": routing.get("action_role") or "relevant_staff",
            "reason": "답변 전 소관 사실 확인이 필요합니다.",
            "instructions": classification.get("needs_fact_check") or ["민원 핵심 요구와 관련 사실 확인"],
        })

    collaborators = [role for role in (routing.get("collaborators") or []) if role and role != routing.get("action_role")]
    if collaborators and handling_route != "FRONT_DESK_RESOLVE" and nature not in {"SAFETY", "INFRINGEMENT_REVIEW"}:
        for role in collaborators:
            actions.append({
                "task_type": "COOP_FACT_CHECK",
                "assignee_role": role,
                "reason": "관련 업무 처리를 위한 협조 확인입니다.",
                "instructions": ["본인 소관의 확인 가능한 사실만 회신", "추정 또는 법적 판단은 하지 않음"],
            })

    risk_signal = bool(
        urgency == "HIGH"
        or infringement_flags
        or special_codes.intersection({"VERBAL_ABUSE_REVIEW", "THREAT_REVIEW", "SAFETY_RISK"})
    )
    if risk_signal and not any(x["task_type"] == "ADMIN_REVIEW" for x in actions):
        actions.append({
            "task_type": "ADMIN_REVIEW",
            "assignee_role": routing.get("approver") or "vice_principal",
            "reason": "우려 행동 신호가 있어 교직원 보호와 대응 방향을 관리자에게 확인합니다.",
            "instructions": ["원문 발화와 맥락 확인", "동석·공동 대응·업무 인수 등 지원 필요 여부 판단"],
        })

    if classification.get("history_review_required") or classification.get("repeat_review"):
        history_action = classification.get("history_action")
        if history_action == "LINK_UNRESOLVED":
            history_reason = "유사한 미해결 민원이 있어 새 민원을 반복으로 종결하지 않고 기존 처리와 연결해야 합니다."
        elif history_action == "REVIEW_FOLLOW_UP":
            history_reason = "기존 답변 이후 새 사실·날짜·요구가 추가된 후속 민원 후보입니다."
        else:
            history_reason = "실질 답변이 완료된 동일 사안의 반복 요구 후보를 검토해야 합니다."
        actions.append({
            "task_type": "HISTORY_REVIEW",
            "assignee_role": "complaint_response_team",
            "reason": history_reason,
            "instructions": [
                "기존 민원의 실질 답변 완료 여부 확인",
                "학교의 미이행 사항 여부 확인",
                "새로운 사실·증거·날짜 추가 여부 확인",
                "요구 내용이 이전과 동일한지 비교",
                "자동 종결하지 말고 담당자가 연결·후속처리·반복검토 중 하나를 확정",
            ],
        })

    return actions


def next_case_state(actions: list[dict[str, Any]]) -> tuple[str, str]:
    types = {a["task_type"] for a in actions}
    if "ADMIN_REVIEW" in types:
        return "IN_PROGRESS", "ADMIN_REVIEW"
    if "FACT_CHECK" in types:
        return "IN_PROGRESS", "FACT_CHECK"
    if "STUDENT_COUNSEL" in types:
        return "IN_PROGRESS", "STUDENT_COUNSEL"
    if "RESPONSE_REVIEW" in types:
        return "RESPONSE_REVIEW", "RESPONSE_REVIEW"
    return "IN_PROGRESS", "FOLLOW_UP"
