"""Explicit fictional fixtures; never called automatically by the server."""
import argparse
import json

from .db import Database, audit, issue_session
from .guardians import issue_guardian_session


def seed(path):
    database = Database(path)
    with database.transaction() as db:
        if db.execute("SELECT 1 FROM memberships LIMIT 1").fetchone():
            raise SystemExit("비어 있는 개발 DB에만 가상 사례를 생성할 수 있습니다.")
        accounts = [("admin", "demo-school", "ADMIN"), ("deputy", "demo-school", "ADMIN"),
                    ("teacher", "demo-school", "TEACHER"), ("outsider", "demo-school", "TEACHER"),
                    ("other-admin", "other-school", "ADMIN")]
        db.executemany("INSERT INTO memberships(user_id, school_id, role) VALUES (?, ?, ?)", accounts)
        db.execute("INSERT INTO cases (id, school_id, title, owner_id, status, version) VALUES ('demo-case', 'demo-school', '[가상] 상담 지원 사례', 'admin', 'OPEN', 1)")
        audit(db, {"user_id": "admin"}, "demo-case", "DEMO_CASE_CREATED", 1, {"fictional": True})
        tokens = {user: issue_session(db, user, school) for user, school, _ in accounts}
        guardians = [('guardian', 'demo-school'), ('other-guardian', 'demo-school'),
                     ('foreign-guardian', 'other-school')]
        db.executemany('INSERT INTO guardian_accounts(guardian_id,school_id) VALUES (?,?)', guardians)
        guardian_tokens = {user: issue_guardian_session(db, user, school) for user, school in guardians}
    return {"notice": "가상 데이터·개발 전용 세션입니다. 세션은 8시간 후 만료됩니다.",
            "tokens": tokens, "guardian_tokens": guardian_tokens}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/private/dev.sqlite3")
    print(json.dumps(seed(parser.parse_args().db), ensure_ascii=False, indent=2))
