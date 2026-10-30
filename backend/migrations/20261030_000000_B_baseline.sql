CREATE TABLE IF NOT EXISTS memberships (
    user_id TEXT NOT NULL,
    school_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('ADMIN', 'TEACHER')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    PRIMARY KEY (user_id, school_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    school_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (user_id, school_id) REFERENCES memberships(user_id, school_id)
);
-- Minimal case integration fixture. A owns intake/classification and the extended case schema.
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    school_id TEXT NOT NULL,
    title TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
    version INTEGER NOT NULL CHECK (version >= 1),
    FOREIGN KEY (owner_id, school_id) REFERENCES memberships(user_id, school_id)
);
CREATE TABLE IF NOT EXISTS case_participants (
    case_id TEXT NOT NULL REFERENCES cases(id),
    user_id TEXT NOT NULL,
    PRIMARY KEY (case_id, user_id)
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    type TEXT NOT NULL CHECK (type IN ('FACT_CHECK', 'COUNSEL', 'CALLBACK', 'FOLLOW_UP')),
    assignee_id TEXT NOT NULL,
    requester_id TEXT NOT NULL,
    question TEXT NOT NULL,
    callback_needed TEXT NOT NULL CHECK (callback_needed IN ('REQUIRED', 'NOT_REQUIRED', 'UNDECIDED')),
    status TEXT NOT NULL CHECK (status IN ('REQUESTED', 'ACKNOWLEDGED', 'COMPLETED')),
    reply TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS support_requests (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    requester_id TEXT NOT NULL,
    coordinator_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('ATTEND', 'JOINT_RESPONSE', 'TAKEOVER', 'URGENT')),
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('REQUESTED', 'ACKNOWLEDGED', 'IN_PROGRESS', 'COMPLETED')),
    result TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS handovers (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    from_owner_id TEXT NOT NULL,
    to_owner_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'ACCEPTED')),
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_handover
    ON handovers(case_id) WHERE status = 'PENDING';
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_version INTEGER NOT NULL,
    new_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_case ON audit_events(case_id, new_version);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
CREATE TABLE IF NOT EXISTS idempotency (
    actor_id TEXT NOT NULL,
    school_id TEXT NOT NULL,
    route TEXT NOT NULL,
    key TEXT NOT NULL,
    body_hash TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response TEXT NOT NULL,
    PRIMARY KEY (actor_id, school_id, route, key)
);
