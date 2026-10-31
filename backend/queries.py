"""Read APIs for the shared case shell and B's work queue."""
import json
from typing import Literal
from fastapi import APIRouter, Query, Request
from .access import accessible_case, authenticate

router = APIRouter()

# Stable presentation order for the fictional walkthrough, interleaving languages,
# teacher protection, information requests, counselling and administration.
DEMO_FEATURED = (
    '중국어 교외체험학습 신청 문의', '교사 대상 폭언 신고', '재학증명서 발급 문의',
    '몽골어 학생 갈등 상담 요청', '홈페이지 사진 삭제 요청', '러시아어 급식비 환불 절차 문의',
    '다국어 가정통신문 요청', '생활지도 상황 확인', '방과후학교 신청 일정',
    '방문 협박 정황 검토', '급식 알레르기 표시 확인', '전학 절차 문의',
    '통합교육 지원 협의', '화장실 시설물 파손', '수행평가 기준 확인',
    '돌봄교실 귀가 동의서', '수업 중 반복 연락 검토', '하교 안전 동선 확인',
    '졸업식 학사일정 문의', '학생 갈등 상담 요청',
)


def demo_order(row):
    return (next((index for index, title in enumerate(DEMO_FEATURED) if title in row['title']),
                 len(DEMO_FEATURED)), row['id'])


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
def list_cases(request: Request, after: str = "", limit: int = Query(50, ge=1, le=100),
               order: Literal['id', 'demo'] = 'id'):
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        demo_listing = order == 'demo' and request.app.state.demo_mode and actor['school_id'] == 'demo-school'
        if demo_listing:
            # Preserve the legacy fixture used as the demo-login integrity marker,
            # but remove its incomplete shell from the visible complaint list.
            rows = db.execute(
                "SELECT c.*,i.channel,i.received_at,i.classification_json FROM cases c "
                "LEFT JOIN case_intakes i ON i.case_id=c.id WHERE c.school_id=? AND c.id<>'demo-case' "
                "AND (?='ADMIN' OR EXISTS (SELECT 1 FROM case_participants p WHERE p.case_id=c.id AND p.user_id=?))",
                (actor['school_id'], actor['role'], actor['user_id']),
            ).fetchall()
            rows = sorted(rows, key=demo_order)
            if after:
                cursor = next((i for i, row in enumerate(rows) if row['id'] == after), None)
                rows = rows[cursor+1:] if cursor is not None else []
            rows = rows[:limit+1]
        else:
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
