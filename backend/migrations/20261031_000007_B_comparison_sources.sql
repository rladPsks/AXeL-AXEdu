CREATE TABLE case_documents (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    kind TEXT NOT NULL CHECK(kind IN ('INTAKE','EVIDENCE','OFFICIAL_DOCUMENT','RESPONSE','ACTION')),
    label TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX documents_case ON case_documents(case_id,id);
CREATE TABLE case_document_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES case_documents(id),
    revision INTEGER NOT NULL CHECK(revision>=1),
    content TEXT NOT NULL,
    provenance TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    delivery_state TEXT NOT NULL CHECK(delivery_state IN ('DELIVERED','NOT_DELIVERED','UNKNOWN','NOT_APPLICABLE')),
    file_id TEXT REFERENCES private_files(id),
    recorded_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(document_id,revision)
);
CREATE TRIGGER document_header_no_update BEFORE UPDATE ON case_documents
BEGIN SELECT RAISE(ABORT,'documents are append-only'); END;
CREATE TRIGGER document_header_no_delete BEFORE DELETE ON case_documents
BEGIN SELECT RAISE(ABORT,'documents are append-only'); END;
CREATE TRIGGER document_version_no_update BEFORE UPDATE ON case_document_versions
BEGIN SELECT RAISE(ABORT,'document versions are append-only'); END;
CREATE TRIGGER document_version_no_delete BEFORE DELETE ON case_document_versions
BEGIN SELECT RAISE(ABORT,'document versions are append-only'); END;
CREATE TABLE case_comparison_profiles (
    case_id TEXT PRIMARY KEY REFERENCES cases(id),
    person_key TEXT,
    issue_key TEXT,
    received_at TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX profile_person ON case_comparison_profiles(person_key,received_at);
CREATE INDEX profile_issue ON case_comparison_profiles(issue_key,received_at);
CREATE TABLE repeat_review_settings (
    school_id TEXT PRIMARY KEY,
    window_days INTEGER NOT NULL CHECK(window_days BETWEEN 1 AND 3650),
    minimum_count INTEGER NOT NULL CHECK(minimum_count BETWEEN 2 AND 1000),
    response_delay_hours INTEGER CHECK(response_delay_hours BETWEEN 1 AND 8760)
);
CREATE TABLE case_relation_events (
    id TEXT PRIMARY KEY,
    left_case_id TEXT NOT NULL REFERENCES cases(id),
    right_case_id TEXT NOT NULL REFERENCES cases(id),
    revision INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('LINKED','SEPARATED')),
    basis TEXT NOT NULL CHECK(basis IN ('SAME_PERSON','SAME_ISSUE','BOTH')),
    reason TEXT NOT NULL,
    recorded_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK(left_case_id<right_case_id),
    UNIQUE(left_case_id,right_case_id,revision)
);
CREATE TRIGGER case_relation_no_update BEFORE UPDATE ON case_relation_events
BEGIN SELECT RAISE(ABORT,'case relations are append-only'); END;
CREATE TRIGGER case_relation_no_delete BEFORE DELETE ON case_relation_events
BEGIN SELECT RAISE(ABORT,'case relations are append-only'); END;
