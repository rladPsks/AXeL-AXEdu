import { useSession } from "../../app/providers";
import type { CaseDetail, Member } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { Badge, Empty, label } from "../../shared/ui";

export function SchoolSupport({
  record,
  members,
}: {
  record: CaseDetail;
  members: Member[];
}) {
  const { session } = useSession();
  const admins = members.filter((m) => m.role === "ADMIN");
  return (
    <>
      <div className="section-heading">
        <h2>학교와 함께 대응하기</h2>
        <span>{record.support_requests.length}건</span>
      </div>
      <p className="hint">
        동석과 공동 대응이 필요할 때 학교의 지원을 요청하세요.
      </p>
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
              요청자 {support.requester_id} · 지원 담당 {support.coordinator_id}
            </p>
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
                지원 담당
                <select required name="coordinator_id" defaultValue="">
                  <option value="" disabled>
                    관리자 선택
                  </option>
                  {admins.map((m) => (
                    <option key={m.user_id}>{m.user_id}</option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              필요한 지원
              <textarea required name="reason" maxLength={10000} />
            </label>
            <p className="notice">
              긴급 도움도 현재는 요청 기록만 저장됩니다. 즉시 도움이 필요하면
              학교 관리자에게 직접 연락해 주세요.
            </p>
          </CommandForm>
        </details>
      ) : null}
    </>
  );
}
