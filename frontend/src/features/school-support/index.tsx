import "../school-support/support-team.css";
import { personName } from "../../shared/names";
import { useScope, useSession } from "../../app/providers";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { recommendSupport, type SupportContact, type SupportIntake } from "./recommendations";
import type { CaseDetail, Member } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { Badge, Empty, ErrorNotice, label } from "../../shared/ui";

export function SchoolSupport({
  record,
  members,
}: {
  record: CaseDetail;
  members: Member[];
}) {
  const { api, session } = useSession();
  const scope = useScope();
  const [selected, setSelected] = useState("");
  const admins = members.filter((m) => m.role === "ADMIN");
  const contacts = useQuery({ queryKey: ["school-contacts", ...scope], queryFn: ({ signal }) => api.get<SupportContact[]>("/api/school/contacts", signal) });
  const intake = useQuery({ queryKey: ["intake", ...scope, record.id], queryFn: ({ signal }) => api.get<SupportIntake>(`/api/cases/${encodeURIComponent(record.id)}/intake`, signal), retry: false });
  const recommendations = recommendSupport(intake.data, contacts.data ?? [], admins.map((m) => m.user_id));
  return (
    <>
      <div className="section-heading">
        <h2>학교와 함께 대응하기</h2>
        <span>{record.support_requests.length}건</span>
      </div>
      <p className="hint">
        동석과 공동 대응이 필요할 때 학교의 지원을 요청하세요.
      </p>
      <section className="support-recommendations" aria-label="지원 요청 대상 추천">
        <h3>이 민원은 누구에게 지원을 요청하면 좋을까요?</h3>
        <p className="meta">요청자: {personName(session.user_id)} · 추천은 민원 유형과 학교 업무분장 기준입니다.</p>
        {contacts.error ? <ErrorNotice error={contacts.error} /> : null}
        {intake.error ? <p className="hint">분류 기록을 불러오지 못해 추천을 표시하지 못했습니다. 아래에서 지원 담당자를 직접 선택할 수 있습니다.</p> : null}
        {contacts.isPending || intake.isPending ? <p role="status">지원 담당자를 확인하는 중…</p> : recommendations.length ? (
          <ol className="routing-ranks">{recommendations.map((candidate, index) => <li key={candidate.user_id}>
            <b>{index + 1}순위 · {candidate.role}</b><strong>{personName(candidate.user_id)}</strong><span>{candidate.reason}</span>
            {record.status === "OPEN" ? <button type="button" onClick={() => { setSelected(candidate.user_id); document.querySelector<HTMLSelectElement>('select[name="coordinator_id"]')?.focus(); }}>이 담당자 선택</button> : null}
          </li>)}</ol>
        ) : !intake.error ? <p className="hint">일치하는 활성 담당자가 없습니다. 학교 업무분장을 확인하고 직접 선택해 주세요.</p> : null}
      </section>
      {record.support_requests.length === 0 ? (
        <Empty>등록된 지원 요청이 없습니다.</Empty>
      ) : (
        record.support_requests.map((support) => (
          <article className="work-item" key={support.id}>
            <div className="item-top">
              <strong>{label(support.type)}</strong>
              <Badge value={support.status} />
            </div>
            <p className="preserve">{support.reason}</p>
            <p className="meta">
              요청자 {personName(support.requester_id)} · 지원 담당{" "}
              {personName(support.coordinator_id)}
            </p>
            {support.requested_coordinator_id &&
            support.requested_coordinator_id !== support.coordinator_id ? (
              <p className="notice">
                요청한 담당 {personName(support.requested_coordinator_id)} 대신{" "}
                {personName(support.coordinator_id)}에게 지원을 연결했습니다.
                민원 총괄은 유지됩니다.
              </p>
            ) : null}
            {support.routing_reason === "NO_AVAILABLE_SUBSTITUTE" ? (
              <p className="notice">
                현재 가능한 업무 대리 담당을 확인하지 못했습니다. 요청은
                저장되었으며 학교 관리자에게 직접 연락해 주세요.
              </p>
            ) : null}
            {support.result ? (
              <blockquote className="preserve">{support.result}</blockquote>
            ) : null}
            {record.status === "OPEN" &&
            session.role === "ADMIN" &&
            session.user_id === support.coordinator_id &&
            support.status !== "COMPLETED" ? (
              <CommandForm
                caseId={record.id}
                version={record.version}
                path={`/api/support-requests/${encodeURIComponent(support.id)}`}
                method="PATCH"
                button="지원 처리 저장"
              >
                <label>
                  처리 상태
                  <select name="status">
                    {(support.status === "REQUESTED"
                      ? ["ACKNOWLEDGED"]
                      : support.status === "ACKNOWLEDGED"
                        ? ["IN_PROGRESS", "COMPLETED"]
                        : ["COMPLETED"]
                    ).map((s) => (
                      <option key={s} value={s}>
                        {label(s)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  지원 내용·결과
                  <textarea
                    name="result"
                    maxLength={10000}
                    placeholder="완료할 때는 지원 결과를 입력해 주세요."
                  />
                </label>
              </CommandForm>
            ) : null}
          </article>
        ))
      )}
      {record.status === "OPEN" ? (
        <details className="new-request" open>
          <summary>학교 지원 요청</summary>
          <CommandForm
            caseId={record.id}
            version={record.version}
            path={`/api/cases/${encodeURIComponent(record.id)}/support-requests`}
            button="지원 요청 보내기"
          >
            <div className="form-row">
              <label>
                지원 종류
                <select name="type">
                  {["ATTEND", "JOINT_RESPONSE", "TAKEOVER", "URGENT"].map(
                    (t) => (
                      <option key={t} value={t}>
                        {label(t)}
                      </option>
                    ),
                  )}
                </select>
              </label>
              <label>
                업무지원자
                <select required name="coordinator_id" value={selected} onChange={(event) => setSelected(event.target.value)}>
                  <option value="" disabled>
                    지원 담당자 선택
                  </option>
                  {admins.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {personName(m.user_id)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              필요한 지원
              <textarea required name="reason" maxLength={10000} />
            </label>
            <p className="notice">
              요청은 담당자의 앱 수신함으로 전달합니다. 실제 수신 확인 전까지
              지원이 확보된 것은 아닙니다. 즉시 도움이 필요하면 학교 관리자에게
              직접 연락해 주세요.
            </p>
          </CommandForm>
        </details>
      ) : null}
    </>
  );
}
