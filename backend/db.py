import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .migration import migrate


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return secrets.token_hex(16)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        migrate(self.path)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


def audit(db, actor, case_id, action, version, payload):
    db.execute(
        "INSERT INTO audit_events (id, case_id, actor_id, action, previous_version, new_version, created_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (uid(), case_id, actor["user_id"], action, version - 1, version, now(),
         json.dumps(payload, ensure_ascii=False)),
    )


def issue_session(db, user_id, school_id):
    """Development fixture only; identity-provider integration is not implemented."""
    token = secrets.token_urlsafe(32)
    expiry = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
    db.execute("INSERT INTO sessions (token_hash, user_id, school_id, expires_at) VALUES (?, ?, ?, ?)",
               (token_hash(token), user_id, school_id, expiry))
    return token
