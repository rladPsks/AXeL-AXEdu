CREATE TABLE support_decisions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    supersedes_id TEXT REFERENCES support_decisions(id),
    decided_by TEXT NOT NULL,
    decision_type TEXT NOT NULL CHECK (decision_type IN ('INTERNAL_SUPPORT','SPECIALIST_SUPPORT','EXTERNAL_SUPPORT','KEEP_REVIEWING')),
    input_case_version INTEGER NOT NULL,
    recorded_case_version INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(case_id, revision),
    UNIQUE(supersedes_id)
);
CREATE TRIGGER support_decisions_no_update BEFORE UPDATE ON support_decisions
BEGIN SELECT RAISE(ABORT, 'support decisions are append-only'); END;
CREATE TRIGGER support_decisions_no_delete BEFORE DELETE ON support_decisions
BEGIN SELECT RAISE(ABORT, 'support decisions are append-only'); END;
