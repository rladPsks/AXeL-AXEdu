import { personName } from "../../shared/names";
import { useQuery } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import { date, Empty, ErrorNotice } from "../../shared/ui";
const names: Record<string, string> = {
  SCHOOL_SETTINGS_UPDATED: "지원·알림 기준 변경",
  ABSENCE_CREATED: "부재·업무 대리자 등록",
  ABSENCE_CANCELLED: "부재 설정 해제",
  RESPONSIBILITY_CREATED: "업무분장 등록",
  RESPONSIBILITY_REMOVED: "업무분장 해제",
  MEMBER_PERMISSION_CHANGED: "구성원 권한 변경",
};
export function SettingsHistory({ version }: { version: number }) {
  const { api } = useSession();
  const scope = useScope();
  const history = useQuery({
    queryKey: ["school-settings-history", ...scope, version],
    queryFn: ({ signal }) =>
      api.get<
        {
          id: string;
          action: string;
          actor_id: string;
          created_at: string;
          payload: Record<string, unknown>;
        }[]
      >("/api/school/settings/timeline", signal),
  });
  return (
    <section className="panel">
      <h2>학교 설정 변경 이력</h2>
      <details>
        <summary>최근 변경 기록 보기</summary>
        {history.isPending ? (
          <p>불러오는 중…</p>
        ) : history.error ? (
          <ErrorNotice error={history.error} />
        ) : history.data.length === 0 ? (
          <Empty>변경 이력이 없습니다.</Empty>
        ) : (
          history.data.map((item) => (
            <article className="work-item" key={item.id}>
              <strong>{names[item.action] ?? "학교 설정 변경"}</strong>
              <p className="meta">
                {personName(item.actor_id)} · {date(item.created_at)}
              </p>
              {typeof item.payload.reason === "string" ? (
                <p>{item.payload.reason}</p>
              ) : null}
            </article>
          ))
        )}
      </details>
    </section>
  );
}
