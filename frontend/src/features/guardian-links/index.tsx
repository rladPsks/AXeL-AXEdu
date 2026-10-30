import { useQuery } from "@tanstack/react-query";
import { personName } from "../../shared/names";
import { useScope, useSession } from "../../app/providers";
import { CommandForm } from "../../shared/CommandForm";
import { Empty, ErrorNotice, date } from "../../shared/ui";
type Link = {
  id: string;
  guardian_id: string;
  verified_by: string;
  verified_at: string;
  verification_note: string;
  active: number;
  revocation_reason: string | null;
};

export function GuardianLinks({
  caseId,
  version,
  closed,
}: {
  caseId: string;
  version: number;
  closed: boolean;
}) {
  const { api } = useSession();
  const scope = useScope();
  const links = useQuery({
    queryKey: ["guardian-links", ...scope, caseId, version],
    queryFn: ({ signal }) =>
      api.get<Link[]>(
        `/api/cases/${encodeURIComponent(caseId)}/guardian-links`,
        signal,
      ),
  });
  return (
    <>
      <h2>보호자 민원 관계 확인</h2>
      <p className="hint">
        본인 확인을 마친 보호자 계정과 민원의 관계를 학교 관리자가 확인합니다.
        연결만으로 교직원 내부 자료가 공개되지는 않습니다.
      </p>
      {links.isPending ? (
        <p>불러오는 중…</p>
      ) : links.error ? (
        <ErrorNotice error={links.error} />
      ) : links.data.length === 0 ? (
        <Empty>확인된 보호자 연결이 없습니다.</Empty>
      ) : (
        links.data.map((link) => (
          <article key={link.id} className="work-item">
            <div className="item-top">
              <strong>{personName(link.guardian_id)}</strong>
              <span className="badge">
                {link.active ? "관계 확인됨" : "연결 해제됨"}
              </span>
            </div>
            <p>{link.verification_note}</p>
            <p className="meta">
              확인자 {personName(link.verified_by)} · {date(link.verified_at)}
            </p>
            {link.active ? (
              <CommandForm
                caseId={caseId}
                version={version}
                path={`/api/guardian-links/${encodeURIComponent(link.id)}/revoke`}
                button="보호자 연결 해제"
              >
                <label>
                  해제 사유
                  <textarea name="reason" required maxLength={10000} />
                </label>
              </CommandForm>
            ) : (
              <p>{link.revocation_reason}</p>
            )}
          </article>
        ))
      )}
      {!closed ? (
        <details className="new-request">
          <summary>확인한 보호자 연결</summary>
          <CommandForm
            caseId={caseId}
            version={version}
            path={`/api/cases/${encodeURIComponent(caseId)}/guardian-links`}
            button="관계 확인 후 연결"
          >
            <label>
              확인된 보호자 계정 ID
              <input name="guardian_id" required maxLength={128} />
            </label>
            <label>
              학교의 관계 확인 근거
              <textarea
                name="verification_note"
                required
                maxLength={10000}
                placeholder="학교에서 관계를 확인한 방법과 필요한 근거를 기록하세요."
              />
            </label>
          </CommandForm>
        </details>
      ) : null}
    </>
  );
}
