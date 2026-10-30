from datetime import datetime, timedelta
from typing import Any
from config import REPEAT_REVIEW_COUNT, REPEAT_WINDOW_DAYS


def apply_rules(result: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    out = dict(result)
    now = datetime.now()
    recent = []
    for item in history:
        try:
            received = datetime.fromisoformat(str(item.get("received_at", "")))
        except (ValueError, TypeError):
            continue
        if now - received <= timedelta(days=REPEAT_WINDOW_DAYS):
            recent.append(item)
    unresolved = any(str(x.get("status", "")).upper() not in {"CLOSED", "RESOLVED"} for x in recent)
    out["repeat_count"] = len(recent) + 1
    out["repeat_review"] = out["repeat_count"] >= REPEAT_REVIEW_COUNT and not unresolved
    if out["repeat_review"]:
        out["infringement_flags"] = list(set(out.get("infringement_flags", []) + ["REPEAT_REVIEW"]))
    if out.get("urgency") == "HIGH" or out.get("stage") == 4 or out["repeat_review"]:
        out["requires_human_review"] = True
    out["escalation_status"] = "PROPOSED" if out.get("stage") == 4 else "NOT_PROPOSED"
    return out
