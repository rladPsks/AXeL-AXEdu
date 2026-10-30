CREATE INDEX IF NOT EXISTS cases_school_status ON cases(school_id, status, id);
CREATE INDEX IF NOT EXISTS participant_user ON case_participants(user_id, case_id);
CREATE INDEX IF NOT EXISTS tasks_case_status ON tasks(case_id, status);
CREATE INDEX IF NOT EXISTS tasks_assignee ON tasks(assignee_id, case_id);
CREATE INDEX IF NOT EXISTS support_case_status ON support_requests(case_id, status);
