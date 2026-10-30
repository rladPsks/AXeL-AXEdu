import json
import sqlite3
from datetime import datetime, timezone
from config import DB_PATH


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS complaints (
          id TEXT PRIMARY KEY, received_at TEXT NOT NULL, channel TEXT, complainant_id TEXT,
          student_ref TEXT, raw_text TEXT NOT NULL, classification_json TEXT, routing_json TEXT,
          response_draft TEXT, status TEXT NOT NULL DEFAULT 'RECEIVED', repeat_count INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS history (
          id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id TEXT NOT NULL, at TEXT NOT NULL,
          actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT
        );
        """)


def save_case(case_id: str, complaint: dict, result: dict):
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        conn.execute("""INSERT OR REPLACE INTO complaints
          (id, received_at, channel, complainant_id, student_ref, raw_text, classification_json,
           routing_json, response_draft, status, repeat_count)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
          (case_id, now, complaint.get("channel", "web"), complaint.get("complainant_id", "DEMO"),
           complaint.get("student_ref", "가명 학생"), complaint["text"],
           json.dumps(result["classification"], ensure_ascii=False), json.dumps(result["routing"], ensure_ascii=False),
           result["response_draft"], "PROPOSED", result["classification"].get("repeat_count", 1)))
        conn.execute("INSERT INTO history (complaint_id, at, actor, action, detail) VALUES (?, ?, ?, ?, ?)",
                     (case_id, now, "agent", "ANALYZED", "분류·라우팅·근거 검색 결과 생성"))


def list_cases():
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM complaints ORDER BY received_at DESC")]
