CREATE TABLE private_files (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    uploader_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('EVIDENCE','SOURCE','AUDIO','EXPORT')),
    visibility TEXT NOT NULL CHECK(visibility IN ('CASE','RESTRICTED')),
    media_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
    sha256 TEXT NOT NULL,
    content BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX private_files_case ON private_files(case_id, created_at, id);
CREATE TABLE file_access_events (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL REFERENCES private_files(id),
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER file_access_no_update BEFORE UPDATE ON file_access_events
BEGIN SELECT RAISE(ABORT, 'file access events are append-only'); END;
CREATE TRIGGER file_access_no_delete BEFORE DELETE ON file_access_events
BEGIN SELECT RAISE(ABORT, 'file access events are append-only'); END;
CREATE TABLE guardian_accounts (
    guardian_id TEXT NOT NULL,
    school_id TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    PRIMARY KEY(guardian_id, school_id)
);
CREATE TABLE guardian_sessions (
    token_hash TEXT PRIMARY KEY,
    guardian_id TEXT NOT NULL,
    school_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(guardian_id, school_id) REFERENCES guardian_accounts(guardian_id, school_id)
);
CREATE TABLE case_guardian_links (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    guardian_id TEXT NOT NULL,
    school_id TEXT NOT NULL,
    verified_by TEXT NOT NULL,
    verification_note TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    revoked_by TEXT,
    revoked_at TEXT,
    revocation_reason TEXT,
    FOREIGN KEY(guardian_id, school_id) REFERENCES guardian_accounts(guardian_id, school_id)
);
CREATE UNIQUE INDEX one_active_guardian_link ON case_guardian_links(case_id, guardian_id) WHERE active=1;
