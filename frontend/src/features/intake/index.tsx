import { useState, type FormEvent } from "react";
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
  workflow: Record<string, any> | null;
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
  const workflow = item.workflow ?? {};
  const tools = workflow.tools ?? {};
  const plan = workflow.action_plan ?? {};
  return (
    <>
      <h2>접수·AI 분류</h2>
      <div className="case-context">
        <span>경로 <strong>{item.channel}</strong></span>
        <span>민원 종류 <strong>{item.complaint_type}</strong></span>
        <span>긴급도 <strong>{cls.urgency ?? "-"}</strong></span>
      </div>
      <section className="work-item">
        <div className="item-top"><strong>AXeL Agent 대응계획</strong><span>{workflow.phase ?? "TRIAGE"}</span></div>
        <p className="hint">LLM 분류 → 공식 근거 RAG → 과거 사건 이력 → 학교 업무분장 순서로 검토한 뒤 필요한 업무만 요청합니다.</p>
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
        {tools.history_review?.history_action && tools.history_review.history_action !== "NONE" ? <><h3>과거 사건 검토</h3><p><strong>{tools.history_review.history_action}</strong> · {tools.history_review.reason}</p></> : null}
        {workflow.initial_response_draft ? <><h3>근거 기반 1차 답변 초안</h3><p className="preserve">{workflow.initial_response_draft}</p><p className="hint">자동 발송되지 않으며 담당자 확인이 필요합니다.</p></> : null}
        <h3>교사 보호 원칙</h3>
        <p>{plan.teacher_scope ?? "교사는 필요한 확인·상담만 수행하고 사건 총괄은 학교 대응체계에 유지합니다."}</p>
        <p><strong>보호자 직접 연락:</strong> {plan.teacher_direct_contact ? "필요 — 학교 지원 방향 확인 후 진행" : "현재 단계에서는 요청하지 않음"}</p>
        <h3>Agent가 사용한 도구</h3>
        <ul>
          <li>LLM 분류: {workflow.agent?.classifier_mode ?? cls.classifier_mode ?? "확인 필요"}</li>
          <li>RAG 공식 근거: {(tools.rag ?? []).length}건 검색</li>
          <li>과거 관련 사건: {(tools.history ?? []).length}건 확인</li>
          <li>업무분장: {tools.duty?.duty_label ?? routing.duty_label ?? "학교별 확인 필요"}</li>
        </ul>
        {(tools.rag ?? []).length ? <details><summary>검색한 공식 근거 보기</summary><ul>{tools.rag.map((x: any, i: number) => <li key={i}><strong>{x.title ?? x.source_id}</strong>{x.article ? ` · ${x.article}` : ""}{x.pdf_page ? ` · PDF p.${x.pdf_page}` : ""}<br/><small>{x.text}</small></li>)}</ul></details> : null}
        <p className="hint">AI가 대응계획을 준비하지만 실제 담당·승인·콜백·대외 답변은 학교 권한자가 확정합니다.</p>
      </section>
      <details>
        <summary>민원 원문 보기</summary>
        <p className="preserve">{item.raw_text}</p>
      </details>
    </>
  );
}
