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
        item["has_response"] = bool(item.get("response_draft"))
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
    unanswered = [x for x in related if not x.get("has_response")]
    high_similarity = [x for x in related if x["similarity"] >= 0.55]

    repeat_candidate = len(high_similarity) >= 2 and not unanswered
    if unanswered:
        reason = "기존 사건 중 실질 답변이 확인되지 않은 건이 있어 반복 민원 확정보다 미응답 여부를 먼저 확인해야 합니다."
    elif high_similarity:
        reason = "유사한 기존 사건이 있으나 새 사실·요구 변화 여부를 사람이 비교해야 합니다."
    else:
        reason = "동일인 관련 사건은 있으나 현재 문구 기준 동일 사안 유사도가 높지 않습니다."

    return {
        "related_count": len(related),
        "high_similarity_count": len(high_similarity),
        "unresolved_count": len(unresolved),
        "unanswered_count": len(unanswered),
        "repeat_candidate": repeat_candidate,
        "reason": reason,
        "items": related,
    }
