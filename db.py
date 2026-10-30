import json
import sqlite3
from datetime import datetime, timezone
from config import DB_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn, table: str, column: str, ddl: str):
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


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

        CREATE TABLE IF NOT EXISTS cases (
          id TEXT PRIMARY KEY,
          received_at TEXT NOT NULL,
          channel TEXT NOT NULL,
          complainant_id TEXT,
          student_ref TEXT,
          raw_text TEXT NOT NULL,
          status TEXT NOT NULL,
          owner_role TEXT NOT NULL,
          next_action TEXT,
          urgency TEXT,
          classification_json TEXT NOT NULL,
          routing_json TEXT NOT NULL,
          response_draft TEXT,
          intake_json TEXT,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY,
          case_id TEXT NOT NULL,
          task_type TEXT NOT NULL,
          assignee_role TEXT NOT NULL,
          status TEXT NOT NULL,
          reason TEXT NOT NULL,
          instructions_json TEXT NOT NULL,
          due_at TEXT,
          result_text TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(case_id) REFERENCES cases(id)
        );

        CREATE TABLE IF NOT EXISTS case_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          case_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          actor TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(case_id) REFERENCES cases(id)
        );

        CREATE TABLE IF NOT EXISTS ai_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          case_id TEXT NOT NULL,
          run_type TEXT NOT NULL,
          classifier_mode TEXT,
          input_json TEXT NOT NULL,
          output_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(case_id) REFERENCES cases(id)
        );

        CREATE TABLE IF NOT EXISTS support_requests (
          id TEXT PRIMARY KEY,
          case_id TEXT NOT NULL,
          requested_by TEXT NOT NULL,
          support_type TEXT NOT NULL,
          status TEXT NOT NULL,
          note TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(case_id) REFERENCES cases(id)
        );
        """)
        _ensure_column(conn, "cases", "intake_json", "TEXT")


def append_event(case_id: str, event_type: str, actor: str, payload: dict | None = None):
    now = utc_now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO case_events (case_id, event_type, actor, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (case_id, event_type, actor, json.dumps(payload or {}, ensure_ascii=False), now),
        )


def save_ai_run(case_id: str, run_type: str, input_data: dict, output_data: dict):
    now = utc_now()
    classifier_mode = output_data.get("classification", {}).get("classifier_mode")
    with connect() as conn:
        conn.execute(
            """INSERT INTO ai_runs
               (case_id, run_type, classifier_mode, input_json, output_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                case_id,
                run_type,
                classifier_mode,
                json.dumps(input_data, ensure_ascii=False),
                json.dumps(output_data, ensure_ascii=False),
                now,
            ),
        )


def create_case_record(case_id: str, complaint: dict, result: dict, *, status: str, owner_role: str, next_action: str):
    now = utc_now()
    cls = result["classification"]
    routing = result["routing"]
    with connect() as conn:
        conn.execute(
            """INSERT INTO cases
               (id, received_at, channel, complainant_id, student_ref, raw_text, status,
                owner_role, next_action, urgency, classification_json, routing_json,
                response_draft, intake_json, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                case_id,
                now,
                complaint.get("channel", "web"),
                complaint.get("complainant_id"),
                complaint.get("student_ref"),
                complaint["text"],
                status,
                owner_role,
                next_action,
                cls.get("urgency"),
                json.dumps(cls, ensure_ascii=False),
                json.dumps(routing, ensure_ascii=False),
                result.get("response_draft"),
                json.dumps({
                    "received_at": complaint.get("received_at") or now,
                    "complainant_name": complaint.get("complainant_name"),
                    "student_name": complaint.get("student_name"),
                    "complaint_type": complaint.get("complaint_type"),
                    "related_people": complaint.get("related_people") or [],
                    "incident_context": complaint.get("incident_context"),
                    "source_type": complaint.get("source_type", "DIRECT"),
                    "jurisdiction": complaint.get("jurisdiction"),
                }, ensure_ascii=False),
                now,
            ),
        )


def update_case_state(
    case_id: str,
    *,
    status: str | None = None,
    next_action: str | None = None,
    response_draft: str | None = None,
):
    fields = ["updated_at = ?"]
    values: list[object] = [utc_now()]
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if next_action is not None:
        fields.append("next_action = ?")
        values.append(next_action)
    if response_draft is not None:
        fields.append("response_draft = ?")
        values.append(response_draft)
    values.append(case_id)
    with connect() as conn:
        conn.execute(f"UPDATE cases SET {', '.join(fields)} WHERE id = ?", values)


def update_case_owner(case_id: str, owner_role: str, *, next_action: str | None = None):
    fields = ["owner_role = ?", "updated_at = ?"]
    values: list[object] = [owner_role, utc_now()]
    if next_action is not None:
        fields.append("next_action = ?")
        values.append(next_action)
    values.append(case_id)
    with connect() as conn:
        conn.execute(f"UPDATE cases SET {', '.join(fields)} WHERE id = ?", values)


def create_task_record(task: dict):
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """INSERT INTO tasks
               (id, case_id, task_type, assignee_role, status, reason, instructions_json,
                due_at, result_text, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task["id"],
                task["case_id"],
                task["task_type"],
                task["assignee_role"],
                task.get("status", "REQUESTED"),
                task["reason"],
                json.dumps(task.get("instructions", []), ensure_ascii=False),
                task.get("due_at"),
                task.get("result_text"),
                now,
                now,
            ),
        )


def complete_task_record(task_id: str, result_text: str):
    now = utc_now()
    with connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise ValueError(f"업무를 찾을 수 없습니다: {task_id}")
        conn.execute(
            "UPDATE tasks SET status = 'COMPLETED', result_text = ?, updated_at = ? WHERE id = ?",
            (result_text, now, task_id),
        )
        return dict(row)


def create_support_request_record(request: dict):
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """INSERT INTO support_requests
               (id, case_id, requested_by, support_type, status, note, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'REQUESTED', ?, ?, ?)""",
            (
                request["id"],
                request["case_id"],
                request["requested_by"],
                request["support_type"],
                request.get("note", ""),
                now,
                now,
            ),
        )


def get_case(case_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        return dict(row) if row else None


def list_case_tasks(case_id: str) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM tasks WHERE case_id = ? ORDER BY created_at",
            (case_id,),
        )]


def list_case_events(case_id: str) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM case_events WHERE case_id = ? ORDER BY id",
            (case_id,),
        )]


def list_support_requests(case_id: str) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM support_requests WHERE case_id = ? ORDER BY created_at",
            (case_id,),
        )]


def list_cases():
    with connect() as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY received_at DESC").fetchall()
        if rows:
            return [dict(r) for r in rows]
        return [dict(r) for r in conn.execute("SELECT * FROM complaints ORDER BY received_at DESC")]


# Legacy compatibility for the original prototype.
def save_case(case_id: str, complaint: dict, result: dict):
    now = utc_now()
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


def get_latest_ai_run(case_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM ai_runs WHERE case_id = ? ORDER BY id DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        return dict(row) if row else None



def dashboard_metrics() -> dict:
    init_db()
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, received_at, status, classification_json, owner_role FROM cases"
        ).fetchall()]
        delivered = [dict(r) for r in conn.execute(
            """SELECT case_id, MAX(created_at) AS delivered_at
               FROM case_events WHERE event_type = 'RESPONSE_DELIVERED'
               GROUP BY case_id"""
        ).fetchall()]
        overdue = conn.execute(
            """SELECT COUNT(*) AS n FROM tasks
               WHERE status != 'COMPLETED' AND due_at IS NOT NULL AND due_at < ?""",
            (utc_now(),),
        ).fetchone()["n"]
        owner_load_rows = [dict(r) for r in conn.execute(
            """SELECT assignee_role, COUNT(*) AS n FROM tasks
               WHERE status != 'COMPLETED'
               GROUP BY assignee_role ORDER BY n DESC"""
        ).fetchall()]

    delivered_map = {x["case_id"]: x["delivered_at"] for x in delivered}
    durations = []
    type_counts: dict[str, int] = {}
    related_history = 0
    for row in rows:
        try:
            cls = json.loads(row.get("classification_json") or "{}")
        except Exception:
            cls = {}
        domain = cls.get("domain_p55") or cls.get("category") or "기타"
        type_counts[domain] = type_counts.get(domain, 0) + 1
        if cls.get("history_action") in {"LINK_UNRESOLVED", "REVIEW_FOLLOW_UP", "REVIEW_REPEAT"}:
            related_history += 1
        if row["id"] in delivered_map:
            try:
                start = datetime.fromisoformat(row["received_at"])
                end = datetime.fromisoformat(delivered_map[row["id"]])
                durations.append((end - start).total_seconds() / 3600)
            except Exception:
                pass

    total = len(rows)
    return {
        "total_cases": total,
        "open_cases": sum(1 for x in rows if x.get("status") not in {"RESOLVED", "CLOSED"}),
        "resolved_cases": sum(1 for x in rows if x.get("status") in {"RESOLVED", "CLOSED"}),
        "average_processing_hours": round(sum(durations) / len(durations), 2) if durations else None,
        "related_history_rate": round(related_history / total, 4) if total else 0.0,
        "overdue_task_count": int(overdue),
        "type_counts": type_counts,
        "open_task_load": owner_load_rows,
        "metric_note": "related_history_rate는 동일인·동일학생 관련 이력이 연결된 사건 비율이며 교직원 평가 지표가 아닙니다.",
    }
