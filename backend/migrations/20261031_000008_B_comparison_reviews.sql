CREATE TABLE comparison_inputs (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    related_case_id TEXT NOT NULL REFERENCES cases(id),
    case_version INTEGER NOT NULL,
    related_case_version INTEGER NOT NULL,
    requested_by TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK(case_id!=related_case_id)
);
CREATE INDEX comparison_inputs_case ON comparison_inputs(case_id,created_at,id);
CREATE TABLE comparison_reviews (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    related_case_id TEXT NOT NULL REFERENCES cases(id),
    revision INTEGER NOT NULL,
    supersedes_id TEXT REFERENCES comparison_reviews(id),
    input_id TEXT NOT NULL REFERENCES comparison_inputs(id),
    recorded_case_version INTEGER NOT NULL,
    related_case_version INTEGER NOT NULL,
    recorded_by TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(case_id,related_case_id,revision),
    UNIQUE(supersedes_id)
);
CREATE TRIGGER comparison_input_no_update BEFORE UPDATE ON comparison_inputs
BEGIN SELECT RAISE(ABORT,'comparison inputs are append-only'); END;
CREATE TRIGGER comparison_input_no_delete BEFORE DELETE ON comparison_inputs
BEGIN SELECT RAISE(ABORT,'comparison inputs are append-only'); END;
CREATE TRIGGER comparison_review_no_update BEFORE UPDATE ON comparison_reviews
BEGIN SELECT RAISE(ABORT,'comparison reviews are append-only'); END;
CREATE TRIGGER comparison_review_no_delete BEFORE DELETE ON comparison_reviews
BEGIN SELECT RAISE(ABORT,'comparison reviews are append-only'); END;
