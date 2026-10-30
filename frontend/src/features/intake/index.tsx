import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { command } from "../../lib/api/client";
import { useScope, useSession } from "../../app/providers";
import { ErrorNotice } from "../../shared/ui";

type IntakeResult = {
  case_id: string;
  version: number;
  classification: Record<string, unknown>;
  routing: Record<string, unknown>;
};

type IntakeRecord = {
  case_id: string;
  received_at: string;
  channel: string;
  complainant_name: string;
  student_name: string | null;
  complaint_type: string;
  related_people: string[];
  incident_context: string | null;
  raw_text: string;
  source_type: string;
  classification: Record<string, any> | null;
  routing: Record<string, any> | null;
};

export function IntakeCreate() {
  const { api } = useSession();
  const scope = useScope();
  const navigate = useNavigate();
  const queries = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.execute<IntakeResult>(command("/api/intakes", body)),
    onSuccess: async (data) => {
      await queries.invalidateQueries({ queryKey: ["cases", ...scope] });
      navigate(`/cases/${encodeURIComponent(data.case_id)}?tab=intake`);
    },
    onError: setError,
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const related = String(form.get("related_people") ?? "")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
    create.mutate({
      channel: String(form.get("channel") ?? "phone"),
      complainant_name: String(form.get("complainant_name") ?? "").trim(),
      student_name: String(form.get("student_name") ?? "").trim() || null,
      complaint_type: String(form.get("complaint_type") ?? "").trim(),
      related_people: related,
      incident_context: String(form.get("incident_context") ?? "").trim() || null,
      raw_text: String(form.get("raw_text") ?? "").trim(),
    });
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <h1>새 민원 접수</h1>
          <p>어느 경로로 들어온 민원이든 한 사건으로 등록하고 AI 분류·업무분장을 함께 준비합니다.</p>
        </div>
      </div>
      <section className="panel">
        <form onSubmit={submit} data-dirty="false">
          <label>
            접수 경로
            <select name="channel" defaultValue="phone">
              <option value="phone">유선전화</option>
              <option value="message">문자·하이톡 등</option>
              <option value="visit">방문</option>
              <option value="ieodream">이어드림</option>
              <option value="homepage">홈페이지</option>
              <option value="external_transfer">교육청·국민신문고 이관</option>
              <option value="other">기타</option>
            </select>
          </label>
          <label>학부모명<input name="complainant_name" required maxLength={120} /></label>
          <label>학생명<input name="student_name" maxLength={120} /></label>
          <label>민원 종류<input name="complaint_type" required maxLength={120} placeholder="예: 생활지도 불만" /></label>
          <label>관련자<input name="related_people" maxLength={500} placeholder="쉼표로 구분" /></label>
          <label>발생 경위<textarea name="incident_context" maxLength={4000} /></label>
          <label>민원 원문<textarea name="raw_text" required maxLength={10000} rows={8} /></label>
          <button className="primary" disabled={create.isPending}>
            {create.isPending ? "분류·접수 중…" : "민원 접수하고 사건 만들기"}
          </button>
        </form>
        {error ? <ErrorNotice error={error} /> : null}
      </section>
    </>
  );
}

export function IntakeDetail({ caseId }: { caseId: string }) {
  const { api } = useSession();
  const scope = useScope();
  const query = useQuery({
    queryKey: ["intake", ...scope, caseId],
    queryFn: ({ signal }) => api.get<IntakeRecord>(`/api/cases/${encodeURIComponent(caseId)}/intake`, signal),
  });
  if (query.isPending) return <p role="status">접수 기록을 불러오는 중…</p>;
  if (query.error) return <ErrorNotice error={query.error} />;
  const item = query.data;
  const cls = item.classification ?? {};
  const routing = item.routing ?? {};
  const labels = routing.role_labels ?? {};
  return (
    <>
      <h2>접수·AI 분류</h2>
      <div className="case-context">
        <span>경로 <strong>{item.channel}</strong></span>
        <span>민원 종류 <strong>{item.complaint_type}</strong></span>
        <span>긴급도 <strong>{cls.urgency ?? "-"}</strong></span>
      </div>
      <section className="work-item">
        <h3>핵심 요구</h3>
        <p>{cls.core_demand ?? cls.summary_for_teacher ?? item.raw_text}</p>
        <h3>처리 경로</h3>
        <p>{cls.handling_route ?? "-"} · 단계 {cls.escalation_level ?? "-"}</p>
        <h3>업무분장 추천</h3>
        <ul>
          <li>1순위 담당: {labels[routing.action_role] ?? routing.action_role ?? "확인 필요"}</li>
          <li>협조: {(routing.collaborators ?? []).map((x: string) => labels[x] ?? x).join(", ") || "없음"}</li>
          <li>승인·조정: {labels[routing.approver] ?? routing.approver ?? "확인 필요"}</li>
          <li>부재 시 대체: {labels[routing.backup_role] ?? routing.backup_role ?? "확인 필요"}</li>
          <li>콜백: {routing.callback_needed ?? "UNDECIDED"}</li>
        </ul>
        <p className="hint">AI 추천이며 실제 담당·승인·콜백 여부는 학교 권한자가 확정합니다.</p>
      </section>
      <details>
        <summary>민원 원문 보기</summary>
        <p className="preserve">{item.raw_text}</p>
      </details>
    </>
  );
}
