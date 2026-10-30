from __future__ import annotations

import json
import uuid
from typing import Any

from db import (
    append_event,
    complete_task_record,
    create_case_record,
    create_support_request_record,
    create_task_record,
    get_case,
    get_latest_ai_run,
    init_db,
    list_case_events,
    list_case_tasks,
    list_support_requests,
    save_ai_run,
    update_case_owner,
    update_case_state,
)
from .action_router import decide_actions, next_case_state
from .history_agent import build_history_review, find_related_cases
from .multilingual import translate_from_korean
from .pipeline import process
from .response_agent import generate_response_draft
from .report_agent import build_support_report
from .validator import validate_response


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _history_from_events(case_id: str) -> list[dict[str, Any]]:
    events = list_case_events(case_id)
    history: list[dict[str, Any]] = []
    for e in events:
        payload = json.loads(e.get("payload_json") or "{}")
        history.append({
            "received_at": e.get("created_at"),
            "status": payload.get("status", "IN_PROGRESS"),
            "event_type": e.get("event_type"),
        })
    return history


def create_case(complaint: dict[str, Any], case_id: str | None = None) -> dict[str, Any]:
    init_db()
    text = str(complaint.get("text", "")).strip()
    if not text:
        raise ValueError("민원 내용이 비어 있습니다.")

    case_id = case_id or _id("CASE")

    # 새 민원 접수 시 같은 보호자/학생의 기존 사건을 먼저 비교한다.
    # '3회 이상' 같은 단순 횟수가 아니라 실질 답변 여부와 새 사실/요구를 함께 본다.
    related = find_related_cases(
        current_case_id=case_id,
        complainant_id=complaint.get("complainant_id"),
        student_ref=complaint.get("student_ref"),
        raw_text=text,
    )
    history_review = build_history_review(
        {"id": case_id, "raw_text": text},
        related,
    )

    # 분류 모델에는 사건 이벤트가 아닌 실제 과거 사건만 history로 전달한다.
    rule_history = [
        {"received_at": x.get("received_at"), "status": x.get("status")}
        for x in related
    ]
    result = process(complaint, history=rule_history)
    cls = result["classification"]
    cls["repeat_count"] = history_review["high_similarity_count"] + 1
    cls["repeat_review"] = history_review["repeat_candidate"]
    cls["history_review_required"] = history_review["history_action"] != "NONE"
    cls["history_action"] = history_review["history_action"]
    cls["history_reason"] = history_review["reason"]
    cls["follow_up_candidate"] = history_review["follow_up_candidate"]
    cls["history_comparison"] = history_review["comparison_summary"]

    consult_reasons = []
    if history_review["history_action"] != "NONE":
        consult_reasons.append("반복·누적 이력 검토")
    if cls.get("handling_route") == "ADMIN_REVIEW":
        consult_reasons.append("관리자 판단 필요")
    if complaint.get("source_type") == "EXTERNAL_TRANSFER":
        consult_reasons.append("외부기관 이관 접수")
    if len(result.get("routing", {}).get("collaborators") or []) >= 2:
        consult_reasons.append("복수 담당 협조 필요")
    cls["team_consult_required"] = bool(consult_reasons)
    cls["team_consult_reasons"] = consult_reasons
    if cls["team_consult_required"]:
        cls["escalation_level"] = max(int(cls.get("escalation_level") or 1), 3)

    actions = decide_actions(cls, result["routing"], result["evidence"])
    status, next_action = next_case_state(actions)
    owner = result["routing"].get("suggested_owner") or "complaint_response_team"

    create_case_record(
        case_id,
        complaint,
        result,
        status=status,
        owner_role=owner,
        next_action=next_action,
    )
    append_event(case_id, "CASE_CREATED", "intake", {"channel": complaint.get("channel", "web")})
    append_event(case_id, "AI_TRIAGE_COMPLETED", "agent", {
        "nature": result["classification"].get("nature"),
        "urgency": result["classification"].get("urgency"),
        "classifier_mode": result["classification"].get("classifier_mode"),
    })
    save_ai_run(case_id, "INITIAL_TRIAGE", complaint, result)
    if history_review["history_action"] != "NONE":
        append_event(case_id, "HISTORY_MATCHED", "agent", {
            "related_count": history_review["related_count"],
            "high_similarity_count": history_review["high_similarity_count"],
            "history_action": history_review["history_action"],
            "repeat_candidate": history_review["repeat_candidate"],
            "follow_up_candidate": history_review["follow_up_candidate"],
            "reason": history_review["reason"],
            "comparison_summary": history_review["comparison_summary"],
        })

    for action in actions:
        task = {
            "id": _id("TASK"),
            "case_id": case_id,
            **action,
            "status": "REQUESTED",
        }
        create_task_record(task)
        append_event(case_id, "TASK_CREATED", "agent", {
            "task_id": task["id"],
            "task_type": task["task_type"],
            "assignee_role": task["assignee_role"],
            "reason": task["reason"],
        })

    return get_case_snapshot(case_id)


FACT_RESULT_TYPES = {"FACT_CHECK", "COOP_FACT_CHECK", "STUDENT_COUNSEL"}
NON_BLOCKING_TYPES = {"SUPPORT_RESPONSE"}


def _confirmed_fact_results(case_id: str) -> list[str]:
    return [
        str(t.get("result_text") or "").strip()
        for t in list_case_tasks(case_id)
        if t.get("status") == "COMPLETED"
        and t.get("task_type") in FACT_RESULT_TYPES
        and str(t.get("result_text") or "").strip()
    ]


def complete_task(task_id: str, result_text: str, actor: str = "staff") -> dict[str, Any]:
    init_db()
    previous = complete_task_record(task_id, result_text)
    case_id = previous["case_id"]
    append_event(case_id, "TASK_COMPLETED", actor, {
        "task_id": task_id,
        "task_type": previous["task_type"],
        "result_text": result_text,
    })

    case = get_case(case_id)
    if case is None:
        raise ValueError(f"사건을 찾을 수 없습니다: {case_id}")

    task_type = previous["task_type"]
    if task_type == "RESPONSE_REVIEW":
        update_case_state(case_id, status="RESPONSE_APPROVED", next_action="AWAITING_DELIVERY")
        append_event(case_id, "RESPONSE_APPROVED", actor, {
            "task_id": task_id,
            "review_note": result_text,
        })
        return get_case_snapshot(case_id)

    confirmed_facts = _confirmed_fact_results(case_id)
    completed_context = "\n".join(f"- {x}" for x in confirmed_facts)
    enriched_text = (
        f"{case['raw_text']}\n\n[학교에서 확인된 사실]\n{completed_context}"
        if completed_context
        else case["raw_text"]
    )
    rerun_input = {
        "text": enriched_text,
        "channel": case["channel"],
        "complainant_id": case.get("complainant_id"),
        "student_ref": case.get("student_ref"),
    }
    rerun = process(rerun_input, history=[])
    response = generate_response_draft(
        complaint_text=case["raw_text"],
        confirmed_facts=confirmed_facts,
        evidence=rerun.get("evidence", []),
        classification=rerun["classification"],
    )
    rerun["response_draft"] = response["draft"]
    rerun["response_generation"] = response
    try:
        original_cls = json.loads(case.get("classification_json") or "{}")
    except Exception:
        original_cls = {}
    target_language = original_cls.get("original_language", "ko")
    translated_response = translate_from_korean(response["draft"], target_language)
    rerun["multilingual"] = {
        "detected_language": target_language,
        "translated_response": translated_response,
    }
    rerun["validation"] = validate_response(
        draft=response["draft"],
        evidence=rerun.get("evidence", []),
        classification=rerun["classification"],
        response_generation=response,
    )
    rerun["internal_task_context"] = {
        "history_reviews": [
            t.get("result_text") for t in list_case_tasks(case_id)
            if t.get("status") == "COMPLETED" and t.get("task_type") == "HISTORY_REVIEW"
        ],
        "admin_reviews": [
            t.get("result_text") for t in list_case_tasks(case_id)
            if t.get("status") == "COMPLETED" and t.get("task_type") == "ADMIN_REVIEW"
        ],
        "support_responses": [
            t.get("result_text") for t in list_case_tasks(case_id)
            if t.get("status") == "COMPLETED" and t.get("task_type") == "SUPPORT_RESPONSE"
        ],
    }
    save_ai_run(case_id, "POST_TASK_REVIEW", rerun_input, rerun)

    blocking_open = [
        t for t in list_case_tasks(case_id)
        if t["status"] != "COMPLETED"
        and t["task_type"] not in NON_BLOCKING_TYPES
        and t["task_type"] != "RESPONSE_REVIEW"
    ]
    if blocking_open:
        next_action = blocking_open[0]["task_type"]
        update_case_state(
            case_id,
            status="IN_PROGRESS",
            next_action=next_action,
            response_draft=rerun["response_draft"],
        )
    else:
        existing_review = [
            t for t in list_case_tasks(case_id)
            if t["task_type"] == "RESPONSE_REVIEW" and t["status"] != "COMPLETED"
        ]
        update_case_state(
            case_id,
            status="RESPONSE_REVIEW",
            next_action="RESPONSE_REVIEW",
            response_draft=rerun["response_draft"],
        )
        if not existing_review:
            review_task = {
                "id": _id("TASK"),
                "case_id": case_id,
                "task_type": "RESPONSE_REVIEW",
                "assignee_role": case.get("owner_role") or "complaint_response_team",
                "status": "REQUESTED",
                "reason": "확인된 사실과 내부 검토를 반영한 답변 초안을 사람이 최종 검토해야 합니다.",
                "instructions": [
                    "보호자 주장과 확인된 사실 구분",
                    "내부 이력·검토 메모가 보호자 답변에 노출되지 않았는지 확인",
                    "미확인 내용·과도한 약속·근거 없는 규정 인용 확인",
                    "승인 후 공식 채널로 전달",
                ],
            }
            create_task_record(review_task)
            append_event(case_id, "TASK_CREATED", "agent", {
                "task_id": review_task["id"],
                "task_type": "RESPONSE_REVIEW",
                "assignee_role": review_task["assignee_role"],
            })

    append_event(case_id, "AI_REVIEW_AFTER_TASK", "agent", {
        "classifier_mode": rerun["classification"].get("classifier_mode"),
        "next_action": get_case(case_id).get("next_action"),
    })
    return get_case_snapshot(case_id)


def deliver_response(
    case_id: str,
    *,
    actor: str = "complaint_response_team",
    channel: str = "official_channel",
    note: str = "",
) -> dict[str, Any]:
    init_db()
    case = get_case(case_id)
    if case is None:
        raise ValueError(f"사건을 찾을 수 없습니다: {case_id}")
    if case.get("status") != "RESPONSE_APPROVED":
        raise ValueError("사람 검토·승인이 완료된 사건만 전달 완료 처리할 수 있습니다.")
    if not str(case.get("response_draft") or "").strip():
        raise ValueError("전달할 답변 초안이 없습니다.")

    update_case_state(case_id, status="RESOLVED", next_action="CLOSED")
    append_event(case_id, "RESPONSE_DELIVERED", actor, {
        "channel": channel,
        "note": note,
    })
    append_event(case_id, "CASE_RESOLVED", actor, {
        "reason": "approved_response_delivered",
    })
    return get_case_snapshot(case_id)

def delegate_case_to_team(
    case_id: str,
    *,
    actor: str,
    note: str = "",
) -> dict[str, Any]:
    init_db()
    case = get_case(case_id)
    if case is None:
        raise ValueError(f"사건을 찾을 수 없습니다: {case_id}")

    update_case_owner(case_id, "complaint_response_team", next_action="TEAM_REVIEW")
    append_event(case_id, "TEACHER_DELEGATED_TO_TEAM", actor, {
        "note": note,
        "previous_owner": case.get("owner_role"),
        "new_owner": "complaint_response_team",
    })

    existing = [
        t for t in list_case_tasks(case_id)
        if t["task_type"] == "TEAM_REVIEW" and t["status"] != "COMPLETED"
    ]
    if not existing:
        task = {
            "id": _id("TASK"),
            "case_id": case_id,
            "task_type": "TEAM_REVIEW",
            "assignee_role": "complaint_response_team",
            "status": "REQUESTED",
            "reason": "교직원이 개인 처리 대신 학교 민원대응팀의 공동 판단·처리를 요청했습니다.",
            "instructions": [
                "현재 사실 확인 결과와 원문 확인",
                "담당·협조·관리자 지원 경로 재확인",
                "교사 개인에게 처리 책임을 되돌리지 말고 대응 방향을 확정",
            ],
        }
        create_task_record(task)
        append_event(case_id, "TASK_CREATED", "agent", {
            "task_id": task["id"],
            "task_type": "TEAM_REVIEW",
            "assignee_role": task["assignee_role"],
        })
    return get_case_snapshot(case_id)


def request_support(
    case_id: str,
    requested_by: str,
    support_type: str,
    note: str = "",
) -> dict[str, Any]:
    init_db()
    allowed = {"JUDGMENT_CONSULT", "ADMIN_PRESENT", "JOINT_RESPONSE", "TAKEOVER_REVIEW", "IMMEDIATE_HELP"}
    if support_type not in allowed:
        raise ValueError(f"지원 유형이 올바르지 않습니다: {support_type}")
    if get_case(case_id) is None:
        raise ValueError(f"사건을 찾을 수 없습니다: {case_id}")

    request = {
        "id": _id("SUPPORT"),
        "case_id": case_id,
        "requested_by": requested_by,
        "support_type": support_type,
        "note": note,
    }
    create_support_request_record(request)
    append_event(case_id, "SUPPORT_REQUESTED", requested_by, {
        "support_request_id": request["id"],
        "support_type": support_type,
        "note": note,
    })

    existing_support = [
        t for t in list_case_tasks(case_id)
        if t["task_type"] == "SUPPORT_RESPONSE" and t["status"] != "COMPLETED"
    ]
    if not existing_support:
        support_task = {
            "id": _id("TASK"),
            "case_id": case_id,
            "task_type": "SUPPORT_RESPONSE",
            "assignee_role": "complaint_response_team",
            "status": "REQUESTED",
            "reason": "교직원의 지원 요청을 검토하고 지원 방식을 확정해야 합니다.",
            "instructions": [support_type, note] if note else [support_type],
        }
        create_task_record(support_task)
        append_event(case_id, "TASK_CREATED", "agent", {
            "task_id": support_task["id"],
            "task_type": "SUPPORT_RESPONSE",
            "assignee_role": support_task["assignee_role"],
        })

    # 지원 요청은 기존 사건 단계(RESPONSE_REVIEW 등)를 덮어쓰지 않는 병렬 업무다.
    return get_case_snapshot(case_id)


def get_case_snapshot(case_id: str) -> dict[str, Any]:
    init_db()
    case = get_case(case_id)
    if case is None:
        raise ValueError(f"사건을 찾을 수 없습니다: {case_id}")

    item = dict(case)
    for key in ("classification_json", "routing_json"):
        if item.get(key):
            item[key[:-5]] = json.loads(item[key])
        item.pop(key, None)
    if item.get("intake_json"):
        try:
            item["intake"] = json.loads(item["intake_json"])
        except Exception:
            item["intake"] = {}
    item.pop("intake_json", None)
    routing = item.get("routing") or {}
    labels = routing.get("role_labels") or {}
    tasks = list_case_tasks(case_id)
    for task in tasks:
        task["assignee_label"] = labels.get(task.get("assignee_role"), task.get("assignee_role"))
        task["backup_role"] = routing.get("backup_role")
        task["backup_label"] = labels.get(routing.get("backup_role"), routing.get("backup_role"))
        task["support_role"] = routing.get("approver") or item.get("owner_role")
        task["support_label"] = labels.get(task["support_role"], task["support_role"])
        task["recommended_timing"] = routing.get("notification_timing")
        if task.get("assignee_role") == "HOMEROOM" or task.get("task_type") == "COOP_FACT_CHECK":
            task["callback_needed"] = routing.get("callback_needed", "UNDECIDED")
            task["callback_reason"] = routing.get("callback_reason")
        else:
            task["callback_needed"] = "NOT_REQUIRED"
            task["callback_reason"] = "담당 부서 또는 대응팀이 우선 처리"

    return {
        "case": item,
        "tasks": tasks,
        "events": list_case_events(case_id),
        "support_requests": list_support_requests(case_id),
    }


def review_case_history(case_id: str) -> dict[str, Any]:
    init_db()
    case = get_case(case_id)
    if case is None:
        raise ValueError(f"사건을 찾을 수 없습니다: {case_id}")
    related = find_related_cases(
        current_case_id=case_id,
        complainant_id=case.get("complainant_id"),
        student_ref=case.get("student_ref"),
        raw_text=case["raw_text"],
    )
    review = build_history_review(case, related)
    append_event(case_id, "HISTORY_REVIEWED", "agent", {
        "related_count": review["related_count"],
        "repeat_candidate": review["repeat_candidate"],
        "reason": review["reason"],
    })
    return review


def generate_support_report(case_id: str) -> dict[str, Any]:
    snapshot = get_case_snapshot(case_id)
    report = build_support_report(snapshot)
    append_event(case_id, "SUPPORT_REPORT_DRAFTED", "agent", {
        "report_status": report["report_status"],
    })
    return report


def get_case_evidence(case_id: str) -> dict[str, Any]:
    init_db()
    if get_case(case_id) is None:
        raise ValueError(f"사건을 찾을 수 없습니다: {case_id}")
    run = get_latest_ai_run(case_id)
    if run is None:
        return {
            "run_type": None,
            "classification_basis": {},
            "routing_basis": {},
            "evidence": [],
            "response_basis": {},
        }

    output = json.loads(run.get("output_json") or "{}")
    classification = output.get("classification", {})
    routing = output.get("routing", {})
    response_generation = output.get("response_generation", {})

    evidence = []
    for item in output.get("evidence", []):
        citation = item.get("citation") or {}
        evidence.append({
            "title": item.get("title"),
            "source_id": item.get("source_id"),
            "source_type": item.get("source_type"),
            "article": item.get("article") or citation.get("article"),
            "pdf_page": item.get("pdf_page") or citation.get("pdf_page"),
            "printed_page": item.get("printed_page") or citation.get("printed_page"),
            "score": item.get("score"),
            "verification_status": item.get("verification_status"),
            "text": item.get("text"),
        })

    return {
        "run_type": run.get("run_type"),
        "created_at": run.get("created_at"),
        "classification_basis": {
            "stage_reason": classification.get("stage_reason"),
            "urgency_reason": classification.get("urgency_reason"),
            "infringement_evidence": classification.get("infringement_evidence", []),
        },
        "routing_basis": {
            "reason": routing.get("reason"),
            "source_pages": routing.get("source_pages", []),
            "requires_human_review": routing.get("requires_human_review"),
        },
        "evidence": evidence,
        "validation": output.get("validation", {}),
        "multilingual": output.get("multilingual", {}),
        "response_basis": {
            "basis_summary": response_generation.get("basis_summary", []),
            "missing_information": response_generation.get("missing_information", []),
            "claims_requiring_review": response_generation.get("claims_requiring_review", []),
            "ready_for_human_review": response_generation.get("ready_for_human_review"),
        },
    }



def get_case_explanation(case_id: str) -> dict[str, Any]:
    """제품 UI용 설명 가능한 근거 카드.

    raw DB/검색 점수/전체 chunk를 노출하지 않고, 사람이 판단을 검토하는 데 필요한
    최소 근거만 구조화한다. 개발용 상세 정보는 get_case_evidence()를 사용한다.
    """
    init_db()
    case = get_case(case_id)
    if case is None:
        raise ValueError(f"사건을 찾을 수 없습니다: {case_id}")

    raw = get_case_evidence(case_id)
    cls = json.loads(case.get("classification_json") or "{}")
    history = review_case_history(case_id)

    official_sources = []
    seen = set()
    for item in raw.get("evidence", []):
        key = (
            item.get("source_id"),
            item.get("article"),
            item.get("pdf_page"),
        )
        if key in seen:
            continue
        seen.add(key)
        source_type = item.get("source_type")
        if source_type == "legacy_operational_guidance":
            authority_note = "보조 운영 참고"
        elif source_type in {"law", "decree", "local_rule"}:
            authority_note = "법령 근거"
        elif source_type == "official_manual":
            authority_note = "공식 매뉴얼"
        elif source_type == "policy_plan":
            authority_note = "정책 참고"
        else:
            authority_note = "공식 참고자료"

        location = item.get("article")
        if not location and item.get("printed_page"):
            location = f"인쇄 p.{item.get('printed_page')}"
        elif not location and item.get("pdf_page"):
            location = f"PDF p.{item.get('pdf_page')}"

        official_sources.append({
            "title": item.get("title") or item.get("source_id"),
            "location": location,
            "authority": authority_note,
        })
        if len(official_sources) >= 4:
            break

    response_basis = raw.get("response_basis") or {}
    basis_items = list(response_basis.get("basis_summary") or [])
    confirmed = [
        x for x in basis_items
        if not any(marker in str(x) for marker in ("민원인은", "보호자는", "주장", "요청함"))
    ]
    complainant_claims = [
        x for x in basis_items
        if any(marker in str(x) for marker in ("민원인은", "보호자는", "주장", "요청함"))
    ]
    missing = list(response_basis.get("missing_information") or [])
    review_claims = list(response_basis.get("claims_requiring_review") or [])

    history_card = {
        "status": history.get("history_action", "NONE"),
        "label": {
            "LINK_UNRESOLVED": "이전 미해결 사건 연결 필요",
            "REVIEW_FOLLOW_UP": "새 사실·요구가 있는 후속 민원",
            "REVIEW_REPEAT": "동일 요구 반복 후보",
            "NONE": "반복 이력 특이사항 없음",
        }.get(history.get("history_action"), "반복 이력 검토 필요"),
        "reason": history.get("reason"),
        "related_count": history.get("related_count", 0),
        "new_information": history.get("comparison_summary") or {},
    }

    return {
        "case_id": case_id,
        "judgment": {
            "category": cls.get("domain_p55") or cls.get("category"),
            "nature": cls.get("nature"),
            "urgency": cls.get("urgency"),
            "why": [
                x for x in [
                    raw.get("classification_basis", {}).get("stage_reason"),
                    raw.get("classification_basis", {}).get("urgency_reason"),
                ] if x
            ],
        },
        "facts": {
            "confirmed": confirmed,
            "complainant_claims": complainant_claims,
            "needs_confirmation": missing,
            "human_review": review_claims,
        },
        "official_basis": (
            official_sources
            if cls.get("nature") == "INFO_REQUEST"
            or cls.get("urgency") == "HIGH"
            or cls.get("special_codes")
            or cls.get("infringement_flags")
            else []
        ),
        "history": history_card,
        "validator": raw.get("validation") or {},
        "multilingual": raw.get("multilingual") or {},
        "safety": {
            "human_review_required": True,
            "auto_send": False,
            "note": "AI는 판단 근거와 초안을 제안하며, 최종 회신·법적 판단·제재·외부 이관은 담당자가 확인합니다.",
        },
    }
