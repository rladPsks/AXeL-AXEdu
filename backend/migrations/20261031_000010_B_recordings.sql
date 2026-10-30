CREATE TABLE audio_consents (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    file_id TEXT NOT NULL REFERENCES private_files(id),
    subject TEXT NOT NULL,
    scope TEXT NOT NULL,
    confirmed_by TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    revoked_at TEXT,
    revoked_by TEXT,
    revoke_reason TEXT,
    CHECK((revoked_at IS NULL) = (revoked_by IS NULL))
);
CREATE UNIQUE INDEX one_active_audio_consent ON audio_consents(file_id) WHERE revoked_at IS NULL;
CREATE INDEX audio_consents_case ON audio_consents(case_id, confirmed_at, id);
CREATE TABLE transcripts (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    file_id TEXT NOT NULL REFERENCES private_files(id),
    revision INTEGER NOT NULL CHECK(revision >= 1),
    source_run_id TEXT REFERENCES agent_runs(id),
    segments TEXT NOT NULL,
    reason TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(file_id, revision),
    CHECK((revision = 1 AND source_run_id IS NOT NULL) OR (revision > 1 AND reason IS NOT NULL))
);
CREATE INDEX transcripts_case ON transcripts(case_id, file_id, revision);
CREATE TRIGGER transcripts_no_update BEFORE UPDATE ON transcripts
BEGIN SELECT RAISE(ABORT,'transcripts are append-only'); END;
CREATE TRIGGER transcripts_no_delete BEFORE DELETE ON transcripts
BEGIN SELECT RAISE(ABORT,'transcripts are append-only'); END;
