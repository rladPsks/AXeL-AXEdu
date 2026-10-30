from __future__ import annotations

from typing import Any


def build_support_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    case = snapshot["case"]
    tasks = snapshot["tasks"]
    events = snapshot["events"]
    support_requests = snapshot["support_requests"]

    completed = [
        {
            "task_type": t.get("task_type") or t.get("type"),
            "assignee_role": t.get("assignee_role") or t.get("assignee_id"),
            "result": t.get("result_text") or t.get("reply"),
        }
        for t in tasks
        if t.get("status") == "COMPLETED"
    ]
    pending = [
        {
            "task_type": t["task_type"],
            "assignee_role": t["assignee_role"],
            "reason": t.get("reason"),
        }
        for t in tasks
        if t.get("status") != "COMPLETED"
    ]

    return {
        "report_status": "DRAFT",
        "case_id": case["id"],
        "school_case_summary": {
            "received_at": case.get("received_at"),
            "channel": case.get("channel"),
            "student_ref": case.get("student_ref") or case.get("student_name") or "미상",
            "complaint_summary": case.get("raw_text") or case.get("title") or "",
            "current_status": case.get("status"),
            "owner_role": case.get("owner_role") or case.get("owner_id"),
        },
        "school_actions_completed": completed,
        "pending_work": pending,
        "support_requests": [
            {
                "support_type": x.get("support_type") or x.get("type"),
                "status": x["status"],
                "note": x.get("note") or x.get("reason") or x.get("result"),
            }
            for x in support_requests
        ],
        "timeline": [
            {
                "at": e["created_at"],
                "event": e.get("event_type") or e.get("action"),
                "actor": e.get("actor") or e.get("actor_id"),
            }
            for e in events
        ],
        "missing_information": [
            "관할 교육지원청의 실제 제출 양식·제출 경로 확인",
            "외부 제출 전 학교 권한자 승인",
        ],
        "notice": "교육지원청 지원·이관 검토용 초안입니다. 자동 제출되지 않습니다.",
    }
