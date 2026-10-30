import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { command } from "../../lib/api/client";
import { useScope, useSession } from "../../app/providers";
import type { CaseDetail } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { koreanTime } from "../../shared/dates";
import { channelName } from "../../shared/names";
import { useUnsavedChanges } from "../../shared/useUnsavedChanges";
import { ErrorNotice, date } from "../../shared/ui";

type IntakeResult = {
  case_id: string;
  version: number;
  classification: Record<string, unknown>;
  routing: Record<string, unknown>;
};

type IntakeRecord = {
  case_id: string;
  received_at: string;
  occurred_at: string | null;
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
  const { dirty, setDirty } = useUnsavedChanges();
  const [error, setError] = useState<unknown>(null);
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.execute<IntakeResult>(command("/api/intakes", body)),
    onSuccess: async (data) => {
      setDirty(false);
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
      channel: String(form.get("channel") || "other"),
      complainant_name: String(form.get("complainant_name") ?? "").trim(),
      student_name: String(form.get("student_name") ?? "").trim() || null,
      complaint_type: String(form.get("complaint_type") ?? "").trim(),
      related_people: related,
      occurred_at: form.get("occurred_at")
        ? koreanTime(String(form.get("occurred_at")))
        : null,
      incident_context:
        String(form.get("incident_context") ?? "").trim() || null,
      raw_text: String(form.get("raw_text") ?? "").trim(),
    });
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <h1>새 민원 접수</h1>
          <p>받은 민원을 기록하면 필요한 지원을 함께 준비해요.</p>
        </div>
      </div>
      <section className="panel">
        <form
          onSubmit={submit}
          data-dirty={dirty ? "true" : undefined}
          onChange={() => setDirty(true)}
        >
          <label>
            학부모명
            <input name="complainant_name" required maxLength={120} />
          </label>
          <label>
            학생명
            <input name="student_name" maxLength={120} />
          </label>
          <label>
            민원 종류
            <input
              name="complaint_type"
              required
              maxLength={120}
              placeholder="예: 생활지도, 단순 민원 등"
            />
          </label>
          <label>
            관련자
            <input
              name="related_people"
              maxLength={500}
              placeholder="예: 김○○, 이○○"
            />
          </label>
          <div className="form-row">
            <label>
              접수 경로 (선택)
              <select name="channel" defaultValue="">
                <option value="">접수 경로 선택</option>
                <option value="phone">유선전화</option>
                <option value="message">문자·하이톡 등</option>
                <option value="visit">방문</option>
                <option value="ieodream">이어드림</option>
                <option value="homepage">홈페이지</option>
                <option value="external_transfer">
                  교육청·국민신문고 이관
                </option>
                <option value="other">기타</option>
              </select>
            </label>
            <label>
              발생 일시
              <input type="datetime-local" name="occurred_at" />
              <small className="field-help">
                알고 있는 경우 입력해 주세요. (한국시간)
              </small>
            </label>
          </div>
          <label>
            발생 경위
            <textarea
              name="incident_context"
              placeholder="예: ○○○○년 ○월 ○일, ○○ 관련 민원 발생"
              maxLength={4000}
              aria-describedby="context-help"
            />
            <small className="field-help" id="context-help">
              언제, 어떤 일이 있었는지 간단히 적어 주세요.
            </small>
          </label>
          <label>
            민원 원문
            <textarea
              name="raw_text"
              required
              maxLength={10000}
              rows={8}
              aria-describedby="raw-help"
            />
            <small className="field-help" id="raw-help">
              받은 내용을 그대로 옮겨 주세요.
            </small>
          </label>
          <div className="intake-submit">
            <button className="primary" disabled={create.isPending}>
              {create.isPending ? "분류·접수 중…" : "민원 접수하고 전송하기"}
            </button>
            <p className="hint">
              ※ 접수한 민원은 담당자와 교장·교감 선생님(민원대응팀)에게
              전송돼요.
            </p>
          </div>
        </form>
        {error ? <ErrorNotice error={error} /> : null}
      </section>
    </>
  );
}

export function IntakeDetail({ caseId }: { caseId: string }) {
  const { api, session } = useSession();
  const scope = useScope();
  const record = useQuery({
    queryKey: ["case", ...scope, caseId],
    queryFn: ({ signal }) =>
      api.get<CaseDetail>(`/api/cases/${encodeURIComponent(caseId)}`, signal),
  });
  const query = useQuery({
    queryKey: ["intake", ...scope, caseId],
    queryFn: ({ signal }) =>
      api.get<IntakeRecord>(
        `/api/cases/${encodeURIComponent(caseId)}/intake`,
        signal,
      ),
  });
  if (query.isPending) return <p role="status">접수 기록을 불러오는 중…</p>;
  if (query.error) return <ErrorNotice error={query.error} />;
  const item = query.data;
  const cls = item.classification ?? {};
  const routing = item.routing ?? {};
  const labels = routing.role_labels ?? {};
  const workflow = item.workflow ?? {};
  const card = workflow.teacher_card ?? {};
  const risky =
    (cls.infringement_flags ?? []).length > 0 ||
    cls.nature === "INFRINGEMENT_REVIEW";
  const roles = [
    ...new Set<string>(
      [
        routing.action_role,
        ...(routing.collaborators ?? []),
        routing.backup_role,
      ].filter(Boolean),
    ),
  ].slice(0, 3);
  const url = `/cases/${encodeURIComponent(caseId)}`;
  const urgency: Record<string, string> = {
    HIGH: "긴급",
    MID: "보통",
    LOW: "낮음",
  };
  const categories: Record<string, string> = {
    INFO: "정보성 문의",
    EDU: "교육",
    SAFE: "안전",
    COUNSEL: "상담",
    ADMIN: "행정",
    STAFF: "교직원",
    OTHER: "기타",
  };
  return (
    <>
      <h2>원문에서 담당자 전달까지</h2>
      <section className="work-item">
        <h3>01 학교에서 받은 민원 원문</h3>
        <p className="meta">
          수신 경로: {channelName(item.channel)} · 등록된 유형:{" "}
          {item.complaint_type}
        </p>
        {item.occurred_at ? (
          <p className="meta">발생 일시: {date(item.occurred_at)}</p>
        ) : null}
        <p className="preserve">{item.raw_text}</p>
      </section>
      <section className="work-item">
        <h3>02 유형·긴급도·담당 추천</h3>
        <div className="case-context">
          <span>
            유형{" "}
            <strong>
              {categories[cls.category] ?? cls.domain_p55 ?? "분류 확인 필요"}
            </strong>
          </span>
          <span>
            긴급도 <strong>{urgency[cls.urgency] ?? "확인 필요"}</strong>
          </span>
          <span>
            담당 분야{" "}
            <strong>{routing.duty_label ?? cls.dept ?? "확인 필요"}</strong>
          </span>
        </div>
        <p className="hint">{cls.urgency_reason}</p>
        <ol className="routing-ranks">
          {[0, 1, 2].map((index) => (
            <li key={index}>
              <b>{index + 1}순위</b>
              <strong>
                {roles[index]
                  ? (labels[roles[index]] ?? roles[index])
                  : "학교 업무분장 확인 필요"}
              </strong>
              <span>{index === 0 ? "주 담당 추천" : "협조·대리 후보"}</span>
            </li>
          ))}
        </ol>
        <p className="hint">
          {routing.reason} 후보 순서는 주 담당 → 협조 → 업무 대리 기준이며, 최종
          담당자는 관리자가 확인합니다.
        </p>
        {risky ? (
          <div className="notice">
            <strong>교육활동 침해 소지 · 이관 검토를 제안합니다</strong>
            <p>
              민원대응팀·관리자가 원문과 근거를 검토한 후 이관 여부를
              결정하세요.
            </p>
            <Link to={`${url}?tab=support`}>학교 지원·이관 요청 검토 →</Link>
          </div>
        ) : null}
        {cls.is_informational ? (
          <>
            <h3>정보성 민원 응답 초안</h3>
            <p className="preserve">
              {workflow.initial_response_draft ||
                "추가 사실 확인이 필요해 초안이 보류되었습니다. AI 지원 검토에서 확인하세요."}
            </p>
            <p className="hint">담당자 검토 전에는 발송되지 않습니다.</p>
          </>
        ) : null}
      </section>
      <section className="work-item">
        <h3>03 담임교사를 위한 요약·필요한 행동</h3>
        {session.role === "ADMIN" && record.data ? (
          <CommandForm
            key={`${caseId}-${record.data.version}`}
            caseId={caseId}
            version={record.data.version}
            path={`/api/cases/${encodeURIComponent(caseId)}/teacher-brief`}
            button="요약·행동 수정 저장"
            disabled={record.data.status === "CLOSED" || record.isError}
            onSaved={() => {
              void query.refetch();
            }}
          >
            <label>
              담임교사용 요약
              <textarea
                name="summary"
                required
                maxLength={10000}
                rows={3}
                defaultValue={card.summary ?? cls.summary_for_teacher ?? ""}
              />
            </label>
            <label>
              필요한 행동
              <textarea
                name="action"
                required
                maxLength={10000}
                rows={3}
                defaultValue={card.action ?? cls.action_for_teacher ?? ""}
              />
            </label>
          </CommandForm>
        ) : (
          <>
            <h4>요약</h4>
            <p className="preserve">
              {card.summary ?? cls.summary_for_teacher}
            </p>
            <h4>필요한 행동</h4>
            <p className="preserve">{card.action ?? cls.action_for_teacher}</p>
          </>
        )}
        {record.error ? <ErrorNotice error={record.error} /> : null}
      </section>
      <section className="work-item">
        <h3>04 담당자에게 전달·처리 확인</h3>
        <p>
          검토한 내용을 바탕으로 실제 담당자를 지정하고 확인 업무를 요청하세요.
        </p>
        <Link to={`${url}?tab=tasks`}>담당자 지정·업무 요청 →</Link>
      </section>
      <details>
        <summary>분류 근거·추가 검토</summary>
        <p>
          분류 방식:{" "}
          {workflow.agent?.classifier_mode ??
            cls.classifier_mode ??
            "확인 필요"}
        </p>
        {(workflow.tools?.rag ?? []).map((entry: any, index: number) => (
          <p key={index}>
            <strong>{entry.title ?? entry.source_id}</strong>
            <br />
            {entry.text}
          </p>
        ))}
        <Link to={`${url}?tab=agent-review`}>AI 지원 검토</Link>
      </details>
    </>
  );
}
