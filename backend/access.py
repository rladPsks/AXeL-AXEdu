"""Shared authentication and school/case authorization."""
from .db import now, token_hash

class DomainError(Exception):
    def __init__(self, status, code, message, **details):
        self.status, self.code, self.message, self.details = status, code, message, details


def fail(status, code, message, **details):
    raise DomainError(status, code, message, **details)


def authenticate(db, request):
    value = request.headers.get("Authorization", "")
    if not value.startswith("Bearer "):
        fail(401, "SESSION_REQUIRED", "유효한 세션이 필요합니다.")
    actor = db.execute(
        "SELECT m.* FROM sessions s JOIN memberships m USING(user_id, school_id) "
        "WHERE s.token_hash=? AND s.expires_at>? AND m.active=1",
        (token_hash(value[7:]), now()),
    ).fetchone()
    if actor is None:
        fail(401, "SESSION_INVALID", "세션이 만료되었거나 유효하지 않습니다.")
    return actor


def accessible_case(db, actor, case_id):
    case = db.execute("SELECT * FROM cases WHERE id=? AND school_id=?",
                      (case_id, actor["school_id"])).fetchone()
    # Do not reveal whether an ID belongs to a different school.
    if case is None:
        fail(404, "CASE_NOT_FOUND", "민원을 찾을 수 없습니다.")
    if actor["role"] != "ADMIN" and not db.execute(
        "SELECT 1 FROM case_participants WHERE case_id=? AND user_id=?",
        (case_id, actor["user_id"]),
    ).fetchone():
        fail(403, "CASE_FORBIDDEN", "이 민원에 접근할 권한이 없습니다.")
    return case


def admin(actor):
    if actor["role"] != "ADMIN":
        fail(403, "ROLE_FORBIDDEN", "관리자 권한이 필요합니다.")


def member(db, actor, user_id, role=None):
    row = db.execute("SELECT * FROM memberships WHERE user_id=? AND school_id=? AND active=1",
                     (user_id, actor["school_id"])).fetchone()
    if row is None or (role and row["role"] != role):
        fail(422, "INVALID_MEMBER", "해당 역할의 활성 학교 구성원을 선택하세요.")


def participate(db, case_id, user_id):
    db.execute("INSERT OR IGNORE INTO case_participants (case_id, user_id) VALUES (?, ?)", (case_id, user_id))
