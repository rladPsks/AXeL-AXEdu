import type { ReactNode } from "react";
import { ApiError } from "../lib/api/client";
export const labels: Record<string, string> = {
  OPEN: "진행 중",
  CLOSED: "종결",
  REQUESTED: "확인 대기",
  ACKNOWLEDGED: "확인함",
  IN_PROGRESS: "지원 중",
  COMPLETED: "완료",
  PENDING: "인수 대기",
  ACCEPTED: "인수 완료",
  FACT_CHECK: "사실 확인",
  COUNSEL: "상담",
  CALLBACK: "콜백",
  FOLLOW_UP: "후속 조치",
  ATTEND: "동석",
  JOINT_RESPONSE: "공동 대응",
  TAKEOVER: "인수 지원",
  URGENT: "긴급 도움",
  REQUIRED: "콜백 필요",
  NOT_REQUIRED: "콜백 불필요",
  UNDECIDED: "콜백 판단 대기",
  ADMIN: "관리자",
  TEACHER: "교사",
  TASK_CREATED: "업무 요청",
  TASK_UPDATED: "업무 회신",
  SUPPORT_REQUESTED: "지원 요청",
  SUPPORT_UPDATED: "지원 처리",
  HANDOVER_REQUESTED: "인계 요청",
  HANDOVER_ACCEPTED: "인계 수락",
  CASE_CLOSED: "사건 종결",
  CASE_OPEN: "사건 재개",
  DEMO_CASE_CREATED: "가상 사건 등록",
};
export const label = (value: string) => labels[value] ?? value;
export const date = (value: string) =>
  new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
export function Badge({ value }: { value: string }) {
  return <span className={`badge ${value.toLowerCase()}`}>{label(value)}</span>;
}
export function ErrorNotice({
  error,
  children,
}: {
  error: unknown;
  children?: ReactNode;
}) {
  return (
    <div className="notice error" role="alert">
      <strong>
        {error instanceof Error
          ? error.message
          : "처리 중 오류가 발생했습니다."}
      </strong>
      {error instanceof ApiError && error.requestId ? (
        <small>문의 번호 {error.requestId}</small>
      ) : null}
      {children}
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}
