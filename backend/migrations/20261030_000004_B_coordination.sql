CREATE TABLE school_settings (
    school_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version>=1),
    duty_admin_id TEXT,
    support_ack_minutes INTEGER NOT NULL DEFAULT 60 CHECK(support_ack_minutes BETWEEN 1 AND 10080),
    overdue_grace_minutes INTEGER NOT NULL DEFAULT 0 CHECK(overdue_grace_minutes BETWEEN 0 AND 10080),
    alerts_enabled INTEGER NOT NULL DEFAULT 1 CHECK(alerts_enabled IN(0,1)),
    FOREIGN KEY(duty_admin_id,school_id) REFERENCES memberships(user_id,school_id)
);
CREATE TABLE staff_absences (
    id TEXT PRIMARY KEY,
    school_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    substitute_id TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    note TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    cancelled_by TEXT,
    cancellation_reason TEXT,
    FOREIGN KEY(user_id,school_id) REFERENCES memberships(user_id,school_id),
    FOREIGN KEY(substitute_id,school_id) REFERENCES memberships(user_id,school_id),
    CHECK(user_id<>substitute_id AND starts_at<ends_at)
);
CREATE INDEX absence_lookup ON staff_absences(school_id,user_id,active,starts_at,ends_at);
CREATE TABLE school_responsibilities (
    id TEXT PRIMARY KEY,
    school_id TEXT NOT NULL,
    label TEXT NOT NULL,
    user_id TEXT NOT NULL,
    substitute_id TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)),
    FOREIGN KEY(user_id,school_id) REFERENCES memberships(user_id,school_id),
    FOREIGN KEY(substitute_id,school_id) REFERENCES memberships(user_id,school_id)
);
CREATE TABLE school_audit_events (
    id TEXT PRIMARY KEY,
    school_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_version INTEGER NOT NULL,
    new_version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER school_audit_no_update BEFORE UPDATE ON school_audit_events
BEGIN SELECT RAISE(ABORT,'school events are append-only'); END;
CREATE TRIGGER school_audit_no_delete BEFORE DELETE ON school_audit_events
BEGIN SELECT RAISE(ABORT,'school events are append-only'); END;
CREATE TABLE task_schedules (
    task_id TEXT PRIMARY KEY REFERENCES tasks(id),
    planned_start_at TEXT,
    due_at TEXT,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
ALTER TABLE support_requests ADD COLUMN requested_coordinator_id TEXT;
ALTER TABLE support_requests ADD COLUMN routing_reason TEXT;
ALTER TABLE support_requests ADD COLUMN assigned_at TEXT;
UPDATE support_requests SET requested_coordinator_id=coordinator_id,assigned_at=created_at;
CREATE TABLE inbox_notifications (
    id TEXT PRIMARY KEY,
    school_id TEXT NOT NULL,
    case_id TEXT NOT NULL REFERENCES cases(id),
    recipient_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN('NORMAL','URGENT')),
    dedupe_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUEUED' CHECK(status IN('QUEUED','DELIVERED','ACKNOWLEDGED','FAILED')),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_attempt_at TEXT NOT NULL,
    error_code TEXT,
    created_at TEXT NOT NULL,
    delivered_at TEXT,
    acknowledged_at TEXT,
    FOREIGN KEY(recipient_id,school_id) REFERENCES memberships(user_id,school_id),
    UNIQUE(school_id,recipient_id,dedupe_key)
);
CREATE INDEX inbox_queue ON inbox_notifications(status,next_attempt_at);
CREATE INDEX inbox_recipient ON inbox_notifications(school_id,recipient_id,status,created_at);
CREATE TABLE notification_events (
    id TEXT PRIMARY KEY,
    notification_id TEXT NOT NULL REFERENCES inbox_notifications(id),
    status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER notification_event_no_update BEFORE UPDATE ON notification_events
BEGIN SELECT RAISE(ABORT,'notification events are append-only'); END;
CREATE TRIGGER notification_event_no_delete BEFORE DELETE ON notification_events
BEGIN SELECT RAISE(ABORT,'notification events are append-only'); END;
CREATE TABLE handovers_expanded (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    from_owner_id TEXT NOT NULL,
    to_owner_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN('PENDING','ACCEPTED','DECLINED','CANCELLED')),
    created_at TEXT NOT NULL,
    resolved_by TEXT,
    resolved_at TEXT,
    resolution_reason TEXT
);
INSERT INTO handovers_expanded(id,case_id,from_owner_id,to_owner_id,reason,status,created_at)
SELECT id,case_id,from_owner_id,to_owner_id,reason,status,created_at FROM handovers;
DROP INDEX one_pending_handover;
DROP TABLE handovers;
ALTER TABLE handovers_expanded RENAME TO handovers;
CREATE UNIQUE INDEX one_pending_handover ON handovers(case_id) WHERE status='PENDING';
