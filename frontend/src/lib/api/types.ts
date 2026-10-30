export type Session = {
  user_id: string;
  school_id: string;
  role: "ADMIN" | "TEACHER";
  active: number;
};
export type Page<T> = { items: T[]; next_cursor: string | null };
export type Member = { user_id: string; role: Session["role"] };
export type Task = {
  id: string;
  case_id: string;
  type: string;
  assignee_id: string;
  requester_id: string;
  question: string;
  callback_needed: string;
  status: string;
  reply: string | null;
  created_at: string;
};
export type Support = {
  id: string;
  requester_id: string;
  coordinator_id: string;
  type: string;
  reason: string;
  status: string;
  result: string | null;
  created_at: string;
};
export type Handover = {
  id: string;
  from_owner_id: string;
  to_owner_id: string;
  reason: string;
  status: string;
  created_at: string;
};
export type CaseSummary = {
  id: string;
  school_id: string;
  title: string;
  owner_id: string;
  status: "OPEN" | "CLOSED";
  version: number;
};
export type CaseDetail = CaseSummary & {
  tasks: Task[];
  support_requests: Support[];
  handovers: Handover[];
};
export type TimelineEvent = {
  id: string;
  actor_id: string;
  action: string;
  new_version: number;
  created_at: string;
  payload: Record<string, unknown>;
};
export type MutationResult = {
  case_id: string;
  version: number;
  [key: string]: unknown;
};
