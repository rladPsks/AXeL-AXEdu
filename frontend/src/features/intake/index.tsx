import { personName } from "../../shared/names";
import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { command } from "../../lib/api/client";
import { useScope, useSession } from "../../app/providers";
import type { CaseDetail } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { koreanTime } from "../../shared/dates";
import { channelName, dutyName } from "../../shared/names";
import { useUnsavedChanges } from "../../shared/useUnsavedChanges";
import { ErrorNotice, date } from "../../shared/ui";
import { EvidenceSource, type Evidence } from "../../shared/EvidenceSource";

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
              ※ 민원 내용·긴급도와 업무분장에 따라 담당자를 연결하고 필요한 지원을 준비해요.
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
  const rag = (workflow.tools?.rag ?? []) as Evidence[];
  const ragSearch = workflow.tools?.rag_search;
  const classificationMode = workflow.agent?.classifier_mode ?? cls.classifier_mode;
  const card = workflow.teacher_card ?? {};
  const risky =
    (cls.infringement_flags ?? []).length > 0 ||
    cls.nature === "INFRINGEMENT_REVIEW";
  const recommendations = (routing.recommendations ?? []) as {
    rank: number; role: string; purpose: string; reason: string;
    sources: Evidence[]; reference_evidence: Evidence[];
  }[];
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
        {workflow.multilingual?.translated_text_ko && workflow.multilingual.detected_language !== "ko" ? <details>
          <summary>검색에 사용하는 한국어 번역 보기</summary>
          <p className="preserve">{workflow.multilingual.translated_text_ko}</p>
          <p className="hint">{workflow.multilingual.review_status === "APPROVED" ? "검토 확정된 번역" : "번역 초안 · 원문 의미 대조 필요"}</p>
          {session.role === "ADMIN" ? <Link to={`${url}?tab=translation`}>다국어 원문·번역 대조 →</Link> : null}
        </details> : null}
      </section>
      <section className="work-item">
        <h3>02 유형·긴급도·업무 지원 참고</h3>
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
        <p className="hint">분류: {classificationMode === "DEMO_FIXTURE" ? "시연용 예시 분류 · 실시간 AI 분류 결과가 아닙니다." : classificationMode === "LLM" ? "AI 모델 분류" : classificationMode ?? "분류 방식 확인 필요"}</p>
        <section aria-label="공식 근거 RAG 검색" className="work-item">
          <h4>공식 근거 RAG 검색 · {rag.length}건</h4>
          <p role="status">{ragSearch?.mode === "ON_VIEW_RETRIEVAL" ? "저장된 근거가 없어 현재 접수 내용으로 실제 검색했습니다." : ragSearch ? "접수 내용을 바탕으로 검색한 공식 문서 결과입니다." : "접수 시 저장한 검색 결과입니다."}</p>
          {ragSearch?.searched_at ? <p className="meta">검색 시각: {date(ragSearch.searched_at)}</p> : null}
          {session.role === "ADMIN" && record.data ? <CommandForm
            caseId={caseId} version={record.data.version}
            path={`/api/cases/${encodeURIComponent(caseId)}/intake/rag-search`}
            button="RAG 근거 다시 검색" disabled={record.data.status === "CLOSED" || record.isError}
            onSaved={() => { void query.refetch(); }}
          /> : null}
          {rag.length ? <details open><summary>검색 결과·문서 출처</summary>{rag.map((entry, i) => <EvidenceSource key={i} entry={entry} />)}</details>
            : <p>검색은 완료했지만 관련 근거를 찾지 못했습니다. 학교별 일정·서류·사실은 담당자에게 확인하세요.</p>}
          <p className="hint">검색 결과는 적용 여부를 검토할 자료입니다. 근거 검색이 민원 사실·담당 배정·번역을 확정하지 않습니다.</p>
        </section>
        <p className="notice">현재 사건 총괄 {record.data ? personName(record.data.owner_id) : "확인 중"} · 아래 순위는 민원 분야·긴급도에 따른 지원 후보입니다.</p>
        <ol className="routing-ranks">{recommendations.map(r => <li key={r.rank}>
          <b>{r.rank}순위 · {r.purpose}</b>
          <strong>{dutyName(labels[r.role] ?? r.role)}</strong>
          <p>추천 이유: {r.reason}</p>
          <h4>담당 추천 참고자료</h4>
          {r.sources.map((entry, i) => <EvidenceSource key={i} entry={entry} />)}
          <details><summary>함께 검토할 RAG 자료·출처 ({r.reference_evidence.length}건)</summary>
            <p className="hint">접수 내용으로 검색한 절차 참고자료입니다. 이 자료가 해당 직위를 직접 지정한다는 뜻은 아닙니다.</p>
            {r.reference_evidence.length ? r.reference_evidence.map((entry, i) => <EvidenceSource key={i} entry={entry} />) : <p>저장된 RAG 검색 자료가 없습니다. 공식 근거 확인이 필요합니다.</p>}
          </details>
        </li>)}</ol>
        {!recommendations.length ? <p>담당 추천 자료를 불러오지 못했습니다. 학교 업무분장을 확인하세요.</p> : null}
        <p className="hint">담당·협조·검토 역할을 구분한 제안입니다. 분야 담당자를 우선 연결하며, 실제 배정은 학교 업무분장과 담당자 가용 여부를 확인해 확정합니다.</p>
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
          <EvidenceSource key={index} entry={entry} />
        ))}
        <Link to={`${url}?tab=agent-review`}>AI 지원 검토</Link>
      </details>
    </>
  );
}
