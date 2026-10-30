import { useQuery } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import type { CaseDetail, Member } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { date, Empty, ErrorNotice, label } from "../../shared/ui";

type Activity = {
  id: string;
  staff_id: string;
  recorded_by: string;
  kind: string;
  occurred_at: string;
  duration_seconds: number | null;
  note: string | null;
};

export const activityKinds = [
  "DIRECT_CONTACT",
  "CALLBACK",
  "COUNSEL",
  "TASK_WORK",
  "SUPPORT_ACTION",
];

export const minutes = (seconds: number | null) =>
  seconds === null ? "시간 미기록" : `${Math.round(seconds / 60)}분`;

export function ActivityLog({
  record,
  members,
}: {
  record: CaseDetail;
  members: Member[];
}) {
  const { api, session } = useSession();
  const scope = useScope();
  const list = useQuery({
    queryKey: ["activities", ...scope, record.id],
    queryFn: ({ signal }) =>
      api.get<Activity[]>(
        `/api/cases/${encodeURIComponent(record.id)}/activities`,
        signal,
      ),
  });
  const staff = session.role === "ADMIN" ? members : [];
  return (
    <>
      <h2>활동 기록</h2>
      <p className="hint">
        학부모 직접 응대, 콜백, 상담 등에 쓴 시간을 직접 남깁니다. 시간을
        입력하지 않은 기록은 0분이 아니라 “시간 미기록”으로 표시하며, 교사
        간 순위나 평가에 쓰지 않습니다. 교사는 본인 기록만 보고 관리자는 전체를
        봅니다.
      </p>
      {list.isPending ? (
        <p>기록을 불러오는 중…</p>
      ) : list.error ? (
        <ErrorNotice error={list.error} />
      ) : list.data.length === 0 ? (
        <Empty>남긴 활동 기록이 없습니다.</Empty>
      ) : (
        list.data.map((a) => (
          <article className="work-item" key={a.id}>
            <div className="item-top">
              <strong>{label(a.kind)}</strong>
              <span>{minutes(a.duration_seconds)}</span>
            </div>
            <p className="meta">
              {a.staff_id} · {date(a.occurred_at)}
              {a.recorded_by !== a.staff_id ? ` · 기록 ${a.recorded_by}` : ""}
            </p>
            {a.note ? <p className="preserve">{a.note}</p> : null}
          </article>
        ))
      )}
      <details className="new-request" open>
        <summary>활동 기록 남기기</summary>
        <CommandForm
          caseId={record.id}
          version={record.version}
          path={`/api/cases/${encodeURIComponent(record.id)}/activities`}
          button="활동 기록 저장"
          onSaved={() => void list.refetch()}
          transformValues={(v) => {
            const minute = v.minutes;
            return {
              staff_id: v.staff_id ?? session.user_id,
              kind: v.kind,
              occurred_at: `${String(v.occurred_at)}:00+09:00`,
              duration_seconds:
                minute === null || minute === undefined || minute === ""
                  ? null
                  : Math.round(Number(minute) * 60),
              note: v.note,
            };
          }}
        >
          {session.role === "ADMIN" ? (
            <label>
              대상 담당자
              <select name="staff_id" defaultValue={session.user_id}>
                {staff.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.user_id}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label>
            활동 종류
            <select name="kind">
              {activityKinds.map((k) => (
                <option key={k} value={k}>
                  {label(k)}
                </option>
              ))}
            </select>
          </label>
          <label>
            일시 (한국 시간)
            <input name="occurred_at" type="datetime-local" required />
          </label>
          <label>
            소요 시간 (분, 모르면 비워 두세요)
            <input name="minutes" type="number" min={0} max={1440} step={1} />
          </label>
          <label>
            메모
            <textarea name="note" maxLength={10000} />
          </label>
        </CommandForm>
      </details>
    </>
  );
}
