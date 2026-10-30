from __future__ import annotations
from difflib import SequenceMatcher
from typing import Any

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, " ".join(a.lower().split()), " ".join(b.lower().split())).ratio()

def find_approved_similar_cases_from_rows(*, current_case_id: str, raw_text: str,
                                          rows: list[dict[str, Any]], limit: int = 1) -> list[dict[str, Any]]:
    candidates = []
    for row in rows:
        if row.get("case_id") == current_case_id:
            continue
        score = _similarity(raw_text, str(row.get("raw_text") or ""))
        if score < 0.35:
            continue
        candidates.append({
            "case_id": row.get("case_id"), "similarity": round(score, 3),
            "category": row.get("complaint_type") or "기타",
            "handling_route": row.get("handling_route"),
            "resolution_excerpt": str(row.get("response_draft") or "")[:240],
            "privacy_note": "보호자·학생 식별정보와 과거 민원 원문은 추천 카드에 노출하지 않습니다.",
        })
    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    return candidates[:limit]
