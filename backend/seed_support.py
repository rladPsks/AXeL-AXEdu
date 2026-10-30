"""Idempotent support staff fixtures, restricted to the marked fictional school."""
from .db import Database
from .demo import seeded
from .access import DomainError


def seed_support(path):
    with Database(path).transaction() as db:
        try:
            seeded(db)
        except DomainError:
            return
        # ADMIN is the existing support coordinator permission in this demo.
        for user in ("academic-head", "office-head", "life-head", "work-support"):
            db.execute("INSERT OR IGNORE INTO memberships(user_id,school_id,role) VALUES (?,'demo-school','ADMIN')", (user,))
        for identity, title, user, deputy in (
            ("support-principal", "교장", "admin", "deputy"),
            ("support-deputy", "교감", "deputy", "admin"),
            ("support-academic", "교무부장", "academic-head", "deputy"),
            ("support-office", "행정실장", "office-head", "deputy"),
            ("support-life", "생활부장", "life-head", "deputy"),
            ("support-work", "업무지원", "work-support", "deputy"),
        ):
            db.execute("INSERT OR IGNORE INTO school_responsibilities(id,school_id,label,user_id,substitute_id) VALUES (?,'demo-school',?,?,?)", (identity, title, user, deputy))
        db.execute("UPDATE school_responsibilities SET label='생활부장' WHERE school_id='demo-school' AND label IN ('생활체육부장','생활인성부장')")
        # Replace only the original fixture assignments, preserving custom edits.
        db.execute("UPDATE school_responsibilities SET user_id='life-head' WHERE id='resp-life' AND school_id='demo-school' AND user_id='deputy'")
        db.execute("UPDATE school_responsibilities SET label='교무부장',user_id='academic-head' WHERE id='resp-academic' AND school_id='demo-school' AND user_id='admin' AND label IN ('교무기획부장','교무부장')")
