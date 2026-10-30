"""Checksummed, atomic SQLite migrations, including adoption of the original schema."""
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def statements(script):
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            yield buffer
            buffer = ""
    if buffer.strip():
        # A trailing comment is harmless; incomplete SQL must fail rather than vanish.
        if any(line.strip() and not line.lstrip().startswith("--") for line in buffer.splitlines()):
            raise ValueError("Migration has an incomplete SQL statement")


def migrate(path, directory=None):
    directory = Path(directory) if directory else Path(__file__).with_name("migrations")
    db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                   "(name TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)")
        applied = dict(db.execute("SELECT name, checksum FROM schema_migrations"))
        files = sorted(directory.glob("*.sql"))
        names = {p.name for p in files}
        if set(applied) - names:
            raise RuntimeError("An applied migration is missing from this checkout")
        for file in files:
            script = file.read_text(encoding="utf-8")
            checksum = hashlib.sha256(script.encode()).hexdigest()
            if file.name in applied:
                if applied[file.name] != checksum:
                    raise RuntimeError(f"Applied migration changed: {file.name}")
                continue
            if applied and file.name < max(applied):
                raise RuntimeError(f"Out-of-order migration: {file.name}")
            # A migration must not escape the runner's transaction or attach another DB.
            forbidden = {sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT,
                         sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA}
            db.set_authorizer(lambda action, *args: sqlite3.SQLITE_DENY if action in forbidden else sqlite3.SQLITE_OK)
            try:
                for statement in statements(script):
                    db.execute(statement)
            finally:
                db.set_authorizer(None)
            db.execute("INSERT INTO schema_migrations(name, checksum, applied_at) VALUES (?, ?, ?)",
                       (file.name, checksum, datetime.now(timezone.utc).isoformat()))
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
