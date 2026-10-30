import { personName } from "../../shared/names";
import { caseName } from "../../shared/names";
import { useState } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import { Empty, ErrorNotice, label } from "../../shared/ui";
import { minutes } from "../activity-log";

type Dashboard = {
  period: { from: string; to: string; timezone: string };
  cases: { basis: string; by_status: Record<string, number> };
  tasks: {
    by_type_status: {
      type: string;
      status: string;
      count: number;
      case_ids: string[];
    }[];
  };
  support: {
    requested_in_period: Record<string, number>;
    unacknowledged_now: number;
    unacknowledged_case_ids: string[];
  };
  staff_activity: {
    staff_id: string;
    by_kind: Record<string, number>;
    recorded_seconds: number;
    entries: number;
    entries_without_duration: number;
    case_ids: string[];
  }[];
  notes: string[];
};

const iso = (d: Date) =>
  new Date(d.getTime() + 9 * 3600_000).toISOString().slice(0, 10);

function CaseLinks({ ids }: { ids: string[] }) {
  return (
    <>
      {ids.map((id) => (
        <Link key={id} to={`/cases/${encodeURIComponent(id)}`}>
          {caseName(id)}{" "}
        </Link>
      ))}
    </>
  );
}

export function DashboardPage() {
  const { api, session } = useSession();
  const scope = useScope();
  const [from, setFrom] = useState(iso(new Date(Date.now() - 29 * 86400_000)));
  const [to, setTo] = useState(iso(new Date()));
  const query = useQuery({
    queryKey: ["dashboard", ...scope, from, to],
    enabled: session.role === "ADMIN" && !!from && !!to,
    queryFn: ({ signal }) =>
      api.get<Dashboard>(
        `/api/dashboard?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        signal,
      ),
  });
  if (session.role !== "ADMIN")
    return <Empty>활동·지원 현황은 학교 관리자만 볼 수 있습니다.</Empty>;
  const d = query.data;
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>활동·지원 현황</h1>
          <p>
            발생한 민원에 대하여 필요한 지원 방안을 확인하기 위한 화면입니다.
          </p>
        </div>
        <button
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          새로고침
        </button>
      </div>
      <section className="panel">
        <div className="command-form">
          <label>
            시작일
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </label>
          <label>
            종료일
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </label>
        </div>
        {query.isPending ? (
          <p role="status">현황을 불러오는 중…</p>
        ) : query.error ? (
          <ErrorNotice error={query.error} />
        ) : d ? (
          <>
            <h2>민원 현황</h2>
            <p className="hint">{d.cases.basis}</p>
            <p>
              진행 중 <strong>{d.cases.by_status.OPEN ?? 0}</strong>건 · 종결{" "}
              <strong>{d.cases.by_status.CLOSED ?? 0}</strong>건
            </p>
            <h2>교사 업무 요청</h2>
            {d.tasks.by_type_status.length === 0 ? (
              <Empty>이 기간에 요청한 업무가 없습니다.</Empty>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>종류</th>
                    <th>상태</th>
                    <th>건수</th>
                    <th>민원</th>
                  </tr>
                </thead>
                <tbody>
                  {d.tasks.by_type_status.map((t) => (
                    <tr key={`${t.type}-${t.status}`}>
                      <td>{label(t.type)}</td>
                      <td>{label(t.status)}</td>
                      <td>{t.count}</td>
                      <td>
                        <CaseLinks ids={t.case_ids} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <h2>학교 지원</h2>
            <p>
              이 기간 요청{" "}
              {Object.entries(d.support.requested_in_period)
                .map(([k, v]) => `${label(k)} ${v}건`)
                .join(" · ") || "없음"}
            </p>
            <p>
              <strong>
                아직 확인하지 않은 지원 요청 {d.support.unacknowledged_now}건
              </strong>{" "}
              <CaseLinks ids={d.support.unacknowledged_case_ids} />
            </p>
            <h2>담당자별 기록된 활동</h2>
            {d.staff_activity.length === 0 ? (
              <Empty>이 기간에 남긴 활동 기록이 없습니다.</Empty>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>담당자</th>
                    <th>기록 건수</th>
                    <th>기록된 시간</th>
                    <th>시간 미기록</th>
                    <th>활동 종류</th>
                    <th>민원</th>
                  </tr>
                </thead>
                <tbody>
                  {d.staff_activity.map((s) => (
                    <tr key={s.staff_id}>
                      <td>{personName(s.staff_id)}</td>
                      <td>{s.entries}</td>
                      <td>{minutes(s.recorded_seconds)}</td>
                      <td>{s.entries_without_duration}건</td>
                      <td>
                        {Object.entries(s.by_kind)
                          .map(([k, v]) => `${label(k)} ${v}`)
                          .join(" · ")}
                      </td>
                      <td>
                        <CaseLinks ids={s.case_ids} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <ul className="hint">
              {d.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </>
        ) : null}
      </section>
    </>
  );
}
