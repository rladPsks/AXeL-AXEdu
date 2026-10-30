from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any

from db import connect


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, " ".join(a.lower().split()), " ".join(b.lower().split())).ratio()


def find_approved_similar_cases(
    *,
    current_case_id: str,
    raw_text: str,
    limit: int = 1,
) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT c.id, c.raw_text, c.response_draft, c.classification_json, c.updated_at
               FROM cases c
               WHERE c.id != ?
                 AND c.status IN ('RESOLVED', 'CLOSED')
                 AND c.response_draft IS NOT NULL
               ORDER BY c.updated_at DESC
               LIMIT 100""",
            (current_case_id,),
        ).fetchall()]

    candidates = []
    for row in rows:
        score = _similarity(raw_text, row.get("raw_text") or "")
        if score < 0.35:
            continue
        try:
            cls = json.loads(row.get("classification_json") or "{}")
        except Exception:
            cls = {}
        candidates.append({
            "case_id": row["id"],
            "similarity": round(score, 3),
            "category": cls.get("domain_p55") or cls.get("category") or "기타",
            "handling_route": cls.get("handling_route"),
            "resolution_excerpt": str(row.get("response_draft") or "")[:240],
            "privacy_note": "보호자·학생 식별정보와 과거 민원 원문은 추천 카드에 노출하지 않습니다.",
        })

    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    return candidates[:limit]
