"""Read APIs for the shared case shell and B's work queue."""
import json
from fastapi import APIRouter, Query, Request
from .access import accessible_case, authenticate

router = APIRouter()


def complaint_stage(classification):
    if not classification:
        return None
    item = json.loads(classification)
    if (item.get("infringement_flags") or item.get("special_codes")
            or item.get("nature") in {"SAFETY", "INFRINGEMENT_REVIEW"}
            or item.get("urgency") in {"HIGH", "URGENT"}
            or (isinstance(item.get("stage"), (int, float)) and item["stage"] >= 4)):
        return "together"
    if item.get("is_informational") or item.get("nature") in {"INFORMATION", "INFO_REQUEST"}:
        return "simple"
    return "review"


@router.get("/api/cases")
def list_cases(request: Request, after: str = "", limit: int = Query(50, ge=1, le=100)):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        rows = db.execute(
            "SELECT c.*,i.channel,i.received_at,i.classification_json FROM cases c "
            "LEFT JOIN case_intakes i ON i.case_id=c.id WHERE c.school_id=? AND c.id>? "
            "AND (?='ADMIN' OR EXISTS (SELECT 1 FROM case_participants p "
            "WHERE p.case_id=c.id AND p.user_id=?)) ORDER BY c.id LIMIT ?",
            (actor["school_id"], after, actor["role"], actor["user_id"], limit + 1),
        ).fetchall()
        items = []
        for row in rows[:limit]:
            item = dict(row)
            item["stage"] = complaint_stage(item.pop("classification_json"))
            items.append(item)
        return {"items": items,
                "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None}


@router.get("/api/my/tasks")
def my_tasks(request: Request, after: str = "", limit: int = Query(50, ge=1, le=100)):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        rows = db.execute(
            "SELECT t.*, c.title AS case_title, c.version AS case_version,s.due_at FROM tasks t "
            "JOIN cases c ON c.id=t.case_id LEFT JOIN task_schedules s ON s.task_id=t.id WHERE c.school_id=? AND t.assignee_id=? "
            "AND t.id>? AND (?='ADMIN' OR EXISTS (SELECT 1 FROM case_participants p "
            "WHERE p.case_id=c.id AND p.user_id=?)) ORDER BY t.id LIMIT ?",
            (actor["school_id"], actor["user_id"], after, actor["role"], actor["user_id"], limit + 1),
        ).fetchall()
        return {"items": [dict(r) for r in rows[:limit]],
                "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None}


@router.get("/api/cases/{case_id}/members")
def case_members(case_id: str, request: Request):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        accessible_case(db, actor, case_id)
        # Teachers need only administrator contacts for support. No token/contact data.
        rows = db.execute(
            "SELECT user_id, role FROM memberships WHERE school_id=? AND active=1 "
            "AND (?='ADMIN' OR role='ADMIN' OR user_id=?) ORDER BY user_id",
            (actor["school_id"], actor["role"], actor["user_id"]),
        )
        return [dict(r) for r in rows]
