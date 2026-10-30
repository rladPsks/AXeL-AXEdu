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
    init_db,
    list_case_events,
    list_case_tasks,
    list_support_requests,
    save_ai_run,
    update_case_state,
)
from .action_router import decide_actions, next_case_state
from .history_agent import build_history_review, find_related_cases
from .pipeline import process
from .response_agent import generate_response_draft
from .report_agent import build_support_report


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
    result = process(complaint)
    actions = decide_actions(result["classification"], result["routing"], result["evidence"])
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


def complete_task(task_id: str, result_text: str, actor: str = "staff") -> dict[str, Any]:
    init_db()
    previous = complete_task_record(task_id, result_text)
    case_id = previous["case_id"]
    append_event(case_id, "TASK_COMPLETED", actor, {
        "task_id": task_id,
        "task_type": previous["task_type"],
        "result_text": result_text,
    })

    # 사람의 확인 결과가 들어오면 기존 원문과 함께 Agent가 다시 사건을 읽는다.
    case = get_case(case_id)
    if case is None:
        raise ValueError(f"사건을 찾을 수 없습니다: {case_id}")

    completed_context = "\n".join(
        f"- {t['task_type']}: {t.get('result_text') or ''}"
        for t in list_case_tasks(case_id)
        if t.get("status") == "COMPLETED"
    )
    enriched_text = (
        f"{case['raw_text']}\n\n"
        f"[학교 내부 확인 결과]\n{completed_context}"
        if completed_context
        else case["raw_text"]
    )
    rerun_input = {
        "text": enriched_text,
        "channel": case["channel"],
        "complainant_id": case.get("complainant_id"),
        "student_ref": case.get("student_ref"),
    }
    rerun = process(rerun_input, history=_history_from_events(case_id))

    confirmed_facts = [
        str(t.get("result_text") or "").strip()
        for t in list_case_tasks(case_id)
        if t.get("status") == "COMPLETED" and str(t.get("result_text") or "").strip()
    ]
    response = generate_response_draft(
        complaint_text=case["raw_text"],
        confirmed_facts=confirmed_facts,
        evidence=rerun.get("evidence", []),
        classification=rerun["classification"],
    )
    rerun["response_draft"] = response["draft"]
    rerun["response_generation"] = response
    save_ai_run(case_id, "POST_TASK_REVIEW", rerun_input, rerun)

    open_tasks = [t for t in list_case_tasks(case_id) if t["status"] != "COMPLETED"]
    if open_tasks:
        next_action = open_tasks[0]["task_type"]
        update_case_state(case_id, status="IN_PROGRESS", next_action=next_action, response_draft=rerun["response_draft"])
    else:
        # 확인 업무가 끝났으면 자동 발송하지 않고 답변 검토 단계로 이동한다.
        update_case_state(
            case_id,
            status="RESPONSE_REVIEW",
            next_action="RESPONSE_REVIEW",
            response_draft=rerun["response_draft"],
        )
        review_task = {
            "id": _id("TASK"),
            "case_id": case_id,
            "task_type": "RESPONSE_REVIEW",
            "assignee_role": case.get("owner_role") or "complaint_response_team",
            "status": "REQUESTED",
            "reason": "사실 확인 결과를 반영한 답변을 검토해야 합니다.",
            "instructions": ["보호자 주장과 확인된 사실을 구분", "미확인 내용·과도한 약속이 없는지 확인", "승인 후 전달"],
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
    update_case_state(case_id, status="IN_PROGRESS", next_action="SUPPORT_RESPONSE")
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
    return {
        "case": item,
        "tasks": list_case_tasks(case_id),
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
