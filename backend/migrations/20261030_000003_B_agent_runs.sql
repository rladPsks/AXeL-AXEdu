CREATE TABLE agent_runs (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    school_id TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    purpose TEXT NOT NULL,
    input_case_version INTEGER NOT NULL,
    input_refs TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('QUEUED','RUNNING','WAITING_REVIEW','SUCCEEDED','FAILED','CANCELLED')),
    step TEXT NOT NULL,
    generation_mode TEXT NOT NULL CHECK(generation_mode IN ('MODEL','RULE','MANUAL')),
    handler_version TEXT NOT NULL,
    provider_metadata TEXT NOT NULL,
    result TEXT,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL,
    lease_token TEXT,
    lease_until REAL,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    retry_of_run_id TEXT REFERENCES agent_runs(id),
    reviewed_by TEXT,
    reviewed_case_version INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX agent_queue ON agent_runs(status,next_attempt_at,lease_until,created_at);
CREATE INDEX agent_case ON agent_runs(case_id,created_at,id);
CREATE TABLE agent_run_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    status TEXT NOT NULL,
    step TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
CREATE TRIGGER agent_event_no_update BEFORE UPDATE ON agent_run_events
BEGIN SELECT RAISE(ABORT, 'agent run events are append-only'); END;
CREATE TRIGGER agent_event_no_delete BEFORE DELETE ON agent_run_events
BEGIN SELECT RAISE(ABORT, 'agent run events are append-only'); END;
