-- Occurrence is distinct from receipt, and is optional for older records.
ALTER TABLE case_intakes ADD COLUMN occurred_at TEXT;
