import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { useScope, useSession } from "../../app/providers";
import { MetadataAction } from "../../shared/MetadataAction";
import { Empty, ErrorNotice, date } from "../../shared/ui";
type Notification = {
  id: string;
  case_id: string;
  case_title: string;
  kind: string;
  resource_id: string;
  severity: string;
  status: string;
  created_at: string;
  delivered_at: string | null;
  acknowledged_at: string | null;
};
const titles: Record<string, string> = {
  CASE_INTAKE_CREATED: "새 민원이 접수됐어요. 함께 확인해 주세요.",
  TASK_REASSIGNED: "업무 수행자가 변경되었습니다.",
  TASK_CREATED: "새 민원 확인 요청이 왔어요",
  TASK_UPDATED: "요청한 업무에 회신이 있습니다.",
  TASK_SCHEDULE_CHANGED: "업무 일정이 변경되었습니다.",
  TASK_OVERDUE: "기한이 지난 업무를 확인해 주세요.",
  SUPPORT_REQUESTED: "학교 지원 요청을 확인해 주세요.",
  SUPPORT_UPDATED: "학교 지원 처리 상황이 바뀌었습니다.",
  SUPPORT_REROUTED: "업무 대리 담당자로 지원 요청을 맡았습니다.",
  SUPPORT_COORDINATOR_CHANGED: "학교 지원 담당이 변경되었습니다.",
  SUPPORT_SUBSTITUTE_UNAVAILABLE: "지원 업무 대리 담당 확인이 필요합니다.",
  SUPPORT_UNCONFIRMED: "아직 확인되지 않은 지원 요청이 있습니다.",
  HANDOVER_REQUESTED: "총괄 인계 요청이 도착했습니다.",
  HANDOVER_ACCEPTED: "총괄 인수가 완료되었습니다.",
  HANDOVER_DECLINED: "총괄 인계 요청이 거절되었습니다.",
  HANDOVER_CANCELLED: "총괄 인계 요청이 취소되었습니다.",
};
function useInbox() {
  const { api } = useSession();
  const scope = useScope();
  return useQuery({
    queryKey: ["notifications", ...scope],
    queryFn: ({ signal }) =>
      api.get<Notification[]>("/api/notifications", signal),
    refetchInterval: 5000,
  });
}
export function InboxIndicator() {
  const inbox = useInbox();
  const unread =
    inbox.data?.filter((item) => item.status === "DELIVERED").length ?? 0;
  return (
    <Link
      to="/inbox"
      className="inbox-indicator"
      aria-label={`학교 알림 ${unread >= 100 ? "100건 이상" : `${unread}건`} 미확인`}
    >
      학교 알림{" "}
      {unread > 0 ? <strong>{unread >= 100 ? "100+" : unread}</strong> : null}
    </Link>
  );
}
export function Inbox() {
  const inbox = useInbox();
  const queries = useQueryClient();
  const scope = useScope();
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>학교 알림 수신함</h1>
          <p>업무·지원 요청과 학교의 후속 조치를 확인하세요.</p>
        </div>
        <button
          disabled={inbox.isFetching}
          onClick={() => void inbox.refetch()}
        >
          수신함 새로고침
        </button>
      </div>
      <p className="notice">
        아직 읽지 않은 알림을 먼저 최대 100개 표시합니다. 수신함 알림 확인은
        실제 업무 회신이나 지원 수신 확인을 대신하지 않습니다. 긴급한 상황에서는
        학교 관리자에게 직접 연락해 주세요.
      </p>
      <section className="panel">
        {inbox.isPending ? (
          <p>알림을 불러오는 중…</p>
        ) : inbox.error ? (
          <ErrorNotice error={inbox.error} />
        ) : inbox.data.length === 0 ? (
          <Empty>수신함에 전달된 알림이 없습니다.</Empty>
        ) : (
          inbox.data.map((item) => {
            const tab = item.kind.startsWith("SUPPORT")
              ? "support"
              : item.kind.startsWith("HANDOVER")
                ? "handover"
                : "tasks";
            return (
              <article className="work-item" key={item.id}>
                <div className="item-top">
                  <strong>{titles[item.kind] ?? "학교 업무 알림"}</strong>
                  <span className="badge">
                    {item.status === "ACKNOWLEDGED"
                      ? "알림 확인함"
                      : "확인해 주세요"}
                  </span>
                </div>
                {item.severity === "URGENT" ? (
                  <p className="urgent-text">긴급 도움 요청</p>
                ) : null}
                <p className="meta">
                  {item.case_title} · {date(item.created_at)}
                </p>
                <div className="action-row">
                  <Link
                    to={`/cases/${encodeURIComponent(item.case_id)}?tab=${tab}`}
                    onClick={() => {
                      void queries.invalidateQueries({
                        queryKey: ["case", ...scope, item.case_id],
                      });
                      void queries.invalidateQueries({
                        queryKey: ["timeline", ...scope, item.case_id],
                      });
                    }}
                  >
                    이 민원 열기
                  </Link>
                  {item.status === "DELIVERED" ? (
                    <MetadataAction
                      path={`/api/notifications/${encodeURIComponent(item.id)}/acknowledge`}
                    >
                      알림 확인
                    </MetadataAction>
                  ) : null}
                </div>
              </article>
            );
          })
        )}
      </section>
    </>
  );
}
