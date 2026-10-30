from __future__ import annotations

from typing import Any


def build_support_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    case = snapshot["case"]
    tasks = snapshot["tasks"]
    events = snapshot["events"]
    support_requests = snapshot["support_requests"]

    completed = [
        {
            "task_type": t["task_type"],
            "assignee_role": t["assignee_role"],
            "result": t.get("result_text"),
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
            "received_at": case["received_at"],
            "channel": case["channel"],
            "student_ref": case.get("student_ref") or "미상",
            "complaint_summary": case["raw_text"],
            "current_status": case["status"],
            "owner_role": case["owner_role"],
        },
        "school_actions_completed": completed,
        "pending_work": pending,
        "support_requests": [
            {
                "support_type": x["support_type"],
                "status": x["status"],
                "note": x.get("note"),
            }
            for x in support_requests
        ],
        "timeline": [
            {
                "at": e["created_at"],
                "event": e["event_type"],
                "actor": e["actor"],
            }
            for e in events
        ],
        "missing_information": [
            "관할 교육지원청의 실제 제출 양식·제출 경로 확인",
            "외부 제출 전 학교 권한자 승인",
        ],
        "notice": "교육지원청 지원·이관 검토용 초안입니다. 자동 제출되지 않습니다.",
    }
