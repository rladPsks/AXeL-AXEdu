from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any

from db import connect


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip(), b.strip()).ratio()


def find_related_cases(
    *,
    current_case_id: str,
    complainant_id: str | None,
    student_ref: str | None,
    raw_text: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not complainant_id and not student_ref:
        return []
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, received_at, complainant_id, student_ref, raw_text, status, response_draft
               FROM cases
               WHERE id != ?
                 AND ((? IS NOT NULL AND complainant_id = ?)
                   OR (? IS NOT NULL AND student_ref = ?))
               ORDER BY received_at DESC
               LIMIT 20""",
            (current_case_id, complainant_id, complainant_id, student_ref, student_ref),
        ).fetchall()

    candidates = []
    for row in rows:
        item = dict(row)
        score = _similarity(raw_text, item["raw_text"])
        if score < 0.20:
            continue
        item["similarity"] = round(score, 3)
        with connect() as conn:
            events = [r["event_type"] for r in conn.execute(
                "SELECT event_type FROM case_events WHERE case_id = ? ORDER BY id",
                (item["id"],),
            ).fetchall()]
            tasks = [dict(r) for r in conn.execute(
                "SELECT task_type, status FROM tasks WHERE case_id = ?",
                (item["id"],),
            ).fetchall()]
        if "RESPONSE_DELIVERED" in events:
            response_status = "DELIVERED"
        elif "RESPONSE_APPROVED" in events or any(
            t["task_type"] == "RESPONSE_REVIEW" and t["status"] == "COMPLETED" for t in tasks
        ):
            response_status = "REVIEWED"
        elif item.get("response_draft"):
            response_status = "DRAFTED"
        else:
            response_status = "NOT_DRAFTED"
        item["response_status"] = response_status
        item["has_substantive_response"] = response_status in {"REVIEWED", "DELIVERED"}
        candidates.append(item)
    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    return candidates[:limit]


def build_history_review(current_case: dict[str, Any], related: list[dict[str, Any]]) -> dict[str, Any]:
    if not related:
        return {
            "related_count": 0,
            "repeat_candidate": False,
            "reason": "연결할 수 있는 기존 동일인·동일 학생 사건 후보가 없습니다.",
            "items": [],
        }

    unresolved = [x for x in related if x.get("status") not in {"CLOSED", "RESOLVED"}]
    not_substantively_answered = [x for x in related if not x.get("has_substantive_response")]
    high_similarity = [x for x in related if x["similarity"] >= 0.55]
    high_similarity_answered = [x for x in high_similarity if x.get("has_substantive_response")]

    repeat_candidate = bool(high_similarity_answered) and not not_substantively_answered
    if not_substantively_answered:
        reason = "유사한 기존 사건이 있어도 검토·전달까지 끝난 실질 답변이 확인되지 않은 건이 있어 반복 민원으로 보지 않고 미해결 사건을 먼저 연결합니다."
    elif high_similarity_answered:
        reason = "실질 답변이 완료된 유사 사건이 있습니다. 동일 요구 반복인지 새 사실·요구가 추가되었는지 사람이 비교해야 합니다."
    else:
        reason = "동일인 관련 사건은 있으나 실질 답변 완료 이력 또는 충분한 동일 사안 유사도가 확인되지 않습니다."

    return {
        "related_count": len(related),
        "high_similarity_count": len(high_similarity),
        "unresolved_count": len(unresolved),
        "unanswered_count": len(not_substantively_answered),
        "repeat_candidate": repeat_candidate,
        "reason": reason,
        "items": related,
    }
