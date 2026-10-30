CREATE TABLE activity_logs (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    school_id TEXT NOT NULL,
    staff_id TEXT NOT NULL,
    recorded_by TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('DIRECT_CONTACT','CALLBACK','COUNSEL','TASK_WORK','SUPPORT_ACTION')),
    occurred_at TEXT NOT NULL,
    duration_seconds INTEGER CHECK(duration_seconds IS NULL OR (duration_seconds >= 0 AND duration_seconds <= 86400)),
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX activity_logs_school_time ON activity_logs(school_id, occurred_at, id);
CREATE INDEX activity_logs_case ON activity_logs(case_id, occurred_at, id);
CREATE TRIGGER activity_logs_no_update BEFORE UPDATE ON activity_logs
BEGIN SELECT RAISE(ABORT,'activity logs are append-only'); END;
CREATE TRIGGER activity_logs_no_delete BEFORE DELETE ON activity_logs
BEGIN SELECT RAISE(ABORT,'activity logs are append-only'); END;
