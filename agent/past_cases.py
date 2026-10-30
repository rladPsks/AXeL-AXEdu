from __future__ import annotations
from difflib import SequenceMatcher
from typing import Any

import json
from db import connect

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

def find_approved_similar_cases(*, current_case_id: str, raw_text: str, limit: int = 1) -> list[dict[str, Any]]:
    """Legacy A-prototype adapter; integrated FastAPI supplies rows to the *_from_rows variant."""
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            """SELECT id,raw_text,response_draft,classification_json,updated_at
               FROM cases WHERE id != ? AND status IN ('RESOLVED','CLOSED')
               AND response_draft IS NOT NULL ORDER BY updated_at DESC LIMIT 100""",
            (current_case_id,),
        ).fetchall()]
    prepared = []
    for row in rows:
        try:
            cls = json.loads(row.get("classification_json") or "{}")
        except Exception:
            cls = {}
        prepared.append({
            "case_id": row["id"], "raw_text": row.get("raw_text"),
            "response_draft": row.get("response_draft"),
            "complaint_type": cls.get("domain_p55") or cls.get("category"),
            "handling_route": cls.get("handling_route"),
        })
    return find_approved_similar_cases_from_rows(
        current_case_id=current_case_id, raw_text=raw_text, rows=prepared, limit=limit
    )
