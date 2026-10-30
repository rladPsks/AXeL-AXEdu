from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from db import connect


HIGH_SIMILARITY = 0.55
NEAR_DUPLICATE = 0.92
REQUEST_TERMS = {
    "확인", "설명", "사과", "면담", "상담", "조치", "조사", "교체", "징계",
    "신고", "교육청", "교육지원청", "동석", "답변", "재발", "보호",
}
STOPWORDS = {
    "우리", "아이", "학생", "선생님", "교사", "학교", "보호자", "학부모",
    "해주세요", "해주", "합니다", "있습니다", "없습니다", "같습니다", "관련",
    "대한", "그리고", "그런데", "때문", "내용", "요청", "문의",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _salient_tokens(text: str) -> set[str]:
    tokens = {
        token for token in re.findall(r"[가-힣A-Za-z0-9]+", _normalize(text))
        if len(token) >= 2 and token not in STOPWORDS
    }
    return tokens


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[./:-]\d+)*", str(text or "")))


def _date_phrases(text: str) -> set[str]:
    return set(re.findall(
        r"(?:\d{1,4}\s*년\s*)?(?:\d{1,2}\s*월\s*)?\d{1,2}\s*일|"
        r"(?:오늘|어제|그제|지난주|이번주|지난달|이번달)",
        str(text or ""),
    ))


def compare_case_text(current_text: str, previous_text: str) -> dict[str, Any]:
    """반복 여부 판단에 필요한 '새 사실/새 요구' 단서를 보수적으로 추출한다.

    법적 판단을 하지 않고 사람이 비교할 수 있는 설명 가능한 특징만 반환한다.
    """
    similarity = _similarity(current_text, previous_text)
    current_tokens = _salient_tokens(current_text)
    previous_tokens = _salient_tokens(previous_text)
    new_terms = sorted(current_tokens - previous_tokens)
    new_numbers = sorted(_numbers(current_text) - _numbers(previous_text))
    new_dates = sorted(_date_phrases(current_text) - _date_phrases(previous_text))

    current_requests = {term for term in REQUEST_TERMS if term in current_text}
    previous_requests = {term for term in REQUEST_TERMS if term in previous_text}
    new_requests = sorted(current_requests - previous_requests)

    # 거의 같은 문장은 표현 차이를 새 사실로 오인하지 않는다.
    lexical_new_detail = similarity < NEAR_DUPLICATE and len(new_terms) >= 2
    has_new_information = bool(new_numbers or new_dates or new_requests or lexical_new_detail)

    return {
        "similarity": round(similarity, 3),
        "has_new_information": has_new_information,
        "new_terms": new_terms[:8],
        "new_numbers": new_numbers[:5],
        "new_dates": new_dates[:5],
        "new_requests": new_requests[:5],
    }


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
        comparison = compare_case_text(raw_text, item["raw_text"])
        if comparison["similarity"] < 0.20:
            continue
        item["similarity"] = comparison["similarity"]
        item["comparison"] = comparison
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
            "high_similarity_count": 0,
            "unresolved_count": 0,
            "unanswered_count": 0,
            "repeat_candidate": False,
            "follow_up_candidate": False,
            "history_action": "NONE",
            "reason": "연결할 수 있는 기존 동일인·동일 학생 사건 후보가 없습니다.",
            "comparison_summary": None,
            "items": [],
        }

    def _has_substantive_response(item: dict[str, Any]) -> bool:
        if "has_substantive_response" in item:
            return bool(item.get("has_substantive_response"))
        return bool(item.get("has_response"))

    high_similarity = [x for x in related if x.get("similarity", 0) >= HIGH_SIMILARITY]
    unresolved = [x for x in high_similarity if x.get("status") not in {"CLOSED", "RESOLVED"}]
    not_substantively_answered = [x for x in high_similarity if not _has_substantive_response(x)]
    answered = [x for x in high_similarity if _has_substantive_response(x)]

    closest_answered = answered[0] if answered else None
    comparison = (closest_answered or high_similarity[0]).get("comparison") if high_similarity else None

    repeat_candidate = False
    follow_up_candidate = False
    history_action = "NONE"

    if not high_similarity:
        reason = "동일인·동일 학생 관련 이력은 있으나 현재 민원과 충분히 유사한 동일 사안 후보는 없습니다."
    elif not_substantively_answered:
        history_action = "LINK_UNRESOLVED"
        reason = (
            "유사한 기존 사건에 검토·전달까지 끝난 실질 답변이 확인되지 않아 "
            "반복 민원으로 보지 않고 미해결 사건과 먼저 연결합니다."
        )
    elif closest_answered:
        comparison = closest_answered.get("comparison") or compare_case_text(
            str(current_case.get("raw_text") or ""),
            str(closest_answered.get("raw_text") or ""),
        )
        if comparison.get("has_new_information"):
            follow_up_candidate = True
            history_action = "REVIEW_FOLLOW_UP"
            reason = (
                "실질 답변이 완료된 유사 사건이 있으나 새 날짜·사실·요구 단서가 추가되어 "
                "동일 반복으로 종결하지 않고 후속 민원으로 검토합니다."
            )
        else:
            repeat_candidate = True
            history_action = "REVIEW_REPEAT"
            reason = (
                "실질 답변이 완료된 높은 유사도의 사건이 있고 뚜렷한 새 사실·요구 단서가 "
                "확인되지 않아 동일 요구 반복 후보로 검토합니다."
            )
    else:
        reason = "유사 사건은 있으나 실질 답변 완료 이력이 확인되지 않습니다."

    return {
        "related_count": len(related),
        "high_similarity_count": len(high_similarity),
        "unresolved_count": len(unresolved),
        "unanswered_count": len(not_substantively_answered),
        "repeat_candidate": repeat_candidate,
        "follow_up_candidate": follow_up_candidate,
        "history_action": history_action,
        "reason": reason,
        "comparison_summary": comparison,
        "items": related,
    }
