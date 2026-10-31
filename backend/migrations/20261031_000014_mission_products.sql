CREATE TABLE case_work_products (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    kind TEXT NOT NULL CHECK(kind IN ('REPORT','RESPONSE','TRANSLATION')),
    revision INTEGER NOT NULL,
    content TEXT NOT NULL,
    source_case_version INTEGER NOT NULL,
    recorded_case_version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('DRAFT','APPROVED','DELIVERED','EXPORTED')),
    decision_id TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(case_id,kind,revision)
);

CREATE TRIGGER case_work_products_no_update BEFORE UPDATE ON case_work_products
BEGIN SELECT RAISE(ABORT,'work products are append-only'); END;
CREATE TRIGGER case_work_products_no_delete BEFORE DELETE ON case_work_products
BEGIN SELECT RAISE(ABORT,'work products are append-only'); END;
