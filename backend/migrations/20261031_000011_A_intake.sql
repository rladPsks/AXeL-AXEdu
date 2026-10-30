CREATE TABLE case_intakes (
    case_id TEXT PRIMARY KEY REFERENCES cases(id),
    received_at TEXT NOT NULL,
    channel TEXT NOT NULL,
    complainant_name TEXT NOT NULL,
    student_name TEXT,
    complaint_type TEXT NOT NULL,
    related_people TEXT NOT NULL DEFAULT '[]',
    incident_context TEXT,
    raw_text TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('DIRECT','EXTERNAL_TRANSFER')),
    classification_json TEXT,
    routing_json TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX case_intakes_received ON case_intakes(received_at);
