import { useSession } from "../../app/providers";
import type { CaseDetail, Member } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { Badge } from "../../shared/ui";
export function Handover({
  record,
  members,
}: {
  record: CaseDetail;
  members: Member[];
}) {
  const { session } = useSession();
  const pending = record.handovers.find((h) => h.status === "PENDING");
  return (
    <>
      <h2>총괄 책임과 인계</h2>
      <p>
        현재 총괄은 <strong>{record.owner_id}</strong>입니다. 지정 인수자가
        수락하기 전까지 기존 총괄의 책임이 유지됩니다.
      </p>
      {record.handovers.map((h) => (
        <article key={h.id} className="work-item">
          <div className="item-top">
            <strong>
              {h.from_owner_id} → {h.to_owner_id}
            </strong>
            <Badge value={h.status} />
          </div>
          <p>{h.reason}</p>
          {h.status === "PENDING" &&
          record.status === "OPEN" &&
          session.user_id === h.to_owner_id ? (
            <CommandForm
              caseId={record.id}
              version={record.version}
              path={`/api/handovers/${encodeURIComponent(h.id)}/accept`}
              button="총괄 인수 수락"
            />
          ) : null}
        </article>
      ))}
      {record.status === "OPEN" &&
      session.user_id === record.owner_id &&
      !pending ? (
        <CommandForm
          caseId={record.id}
          version={record.version}
          path={`/api/cases/${encodeURIComponent(record.id)}/handovers`}
          button="총괄 인계 요청"
        >
          <label>
            인수할 관리자
            <select required name="to_owner_id" defaultValue="">
              <option value="" disabled>
                관리자 선택
              </option>
              {members
                .filter(
                  (m) => m.role === "ADMIN" && m.user_id !== record.owner_id,
                )
                .map((m) => (
                  <option key={m.user_id}>{m.user_id}</option>
                ))}
            </select>
          </label>
          <label>
            인계 사유
            <textarea name="reason" required maxLength={10000} />
          </label>
        </CommandForm>
      ) : null}
      <div className="notice">
        전체 종결은 답변·승인·후속 의무의 통합 검사 연결 후 제공합니다.
      </div>
      {record.status === "CLOSED" && session.user_id === record.owner_id ? (
        <CommandForm
          caseId={record.id}
          version={record.version}
          path={`/api/cases/${encodeURIComponent(record.id)}/reopen`}
          button="사건 재개"
        >
          <label>
            재개 사유
            <textarea name="reason" required maxLength={10000} />
          </label>
        </CommandForm>
      ) : null}
    </>
  );
}
