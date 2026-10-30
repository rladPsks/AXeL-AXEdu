import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import type { Member } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { koreanTime } from "../../shared/dates";
import { MetadataAction } from "../../shared/MetadataAction";
import { Empty, ErrorNotice, date, label } from "../../shared/ui";
import { SettingsHistory } from "./SettingsHistory";

type Absence = {
  id: string;
  user_id: string;
  substitute_id: string;
  starts_at: string;
  ends_at: string;
  note: string | null;
  active: number;
};
type Responsibility = {
  id: string;
  label: string;
  user_id: string;
  substitute_id: string | null;
  active: number;
};
type Settings = {
  version: number;
  duty_admin_id: string | null;
  support_ack_minutes: number;
  overdue_grace_minutes: number;
  alerts_enabled: number;
  absences: Absence[];
  responsibilities: Responsibility[];
};
type Delivery = {
  id: string;
  case_id: string;
  recipient_id: string;
  kind: string;
  severity: string;
  status: string;
  attempts: number;
  error_code: string | null;
};

export function SchoolSettings() {
  const { api, session } = useSession();
  const scope = useScope();
  const [target, setTarget] = useState("");
  const settings = useQuery({
    queryKey: ["school-settings", ...scope],
    queryFn: ({ signal }) => api.get<Settings>("/api/school/settings", signal),
    enabled: session.role === "ADMIN",
  });
  const members = useQuery({
    queryKey: ["school-members", ...scope],
    queryFn: ({ signal }) =>
      api.get<(Member & { active: number })[]>("/api/school/members", signal),
    enabled: session.role === "ADMIN",
  });
  const deliveries = useQuery({
    queryKey: ["notification-status", ...scope],
    queryFn: ({ signal }) =>
      api.get<Delivery[]>("/api/school/notification-status", signal),
    enabled: session.role === "ADMIN",
    refetchInterval: 5000,
  });
  if (session.role !== "ADMIN")
    return (
      <ErrorNotice
        error={new Error("학교 관리자만 설정을 변경할 수 있습니다.")}
      />
    );
  if (settings.isPending) return <p>학교 설정을 불러오는 중…</p>;
  if (settings.error || !settings.data)
    return <ErrorNotice error={settings.error} />;
  const config = settings.data;
  const active = members.data?.filter((m) => m.active) ?? [];
  const admins = active.filter((m) => m.role === "ADMIN");
  const targetRole = active.find((m) => m.user_id === target)?.role;
  const schoolForm = {
    caseId: "school-settings",
    version: config.version,
    versionField: "expected_settings_version" as const,
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>학교 지원 설정</h1>
          <p>업무분장과 부재 대체자, 알림 기준을 관리합니다.</p>
        </div>
        <button
          disabled={settings.isFetching}
          onClick={() => void settings.refetch()}
        >
          설정 새로고침
        </button>
      </div>
      {members.error ? <ErrorNotice error={members.error} /> : null}
      <section className="panel">
        <h2>지원·알림 기준</h2>
        <p className="hint">
          시간 기준은 학교의 운영 설정이며 법정 처리 기한이 아닙니다. 일반
          알림을 꺼도 긴급 도움 알림은 유지됩니다.
        </p>
        <CommandForm
          {...schoolForm}
          path="/api/school/settings"
          method="PUT"
          button="학교 기준 저장"
        >
          <label>
            당번 관리자
            <select
              name="duty_admin_id"
              defaultValue={config.duty_admin_id ?? ""}
            >
              <option value="">미지정</option>
              {admins.map((m) => (
                <option key={m.user_id}>{m.user_id}</option>
              ))}
            </select>
          </label>
          <div className="form-row">
            <label>
              지원 미확인 알림 기준 (분)
              <input
                type="number"
                min="1"
                max="10080"
                required
                name="support_ack_minutes"
                defaultValue={config.support_ack_minutes}
              />
            </label>
            <label>
              업무 기한 후 알림 유예 (분)
              <input
                type="number"
                min="0"
                max="10080"
                required
                name="overdue_grace_minutes"
                defaultValue={config.overdue_grace_minutes}
              />
            </label>
          </div>
          <input type="hidden" name="alerts_enabled" value="false" />
          <label>
            <span>
              <input
                style={{ width: "auto" }}
                type="checkbox"
                name="alerts_enabled"
                value="true"
                defaultChecked={!!config.alerts_enabled}
              />{" "}
              일반 업무 알림 사용
            </span>
          </label>
        </CommandForm>
      </section>
      <section className="panel">
        <h2>구성원 권한과 활성 상태</h2>
        <p className="hint">
          같은 학교의 기존 구성원만 관리합니다. 남은 책임을 정리한 뒤 변경할 수
          있으며, 변경 대상의 기존 세션은 폐기됩니다. 자신의 권한은 다른
          관리자에게 요청하세요.
        </p>
        {members.data?.map((person) => (
          <article className="work-item" key={person.user_id}>
            <div className="item-top">
              <strong>{person.user_id}</strong>
              <span className="badge">
                {label(person.role)} · {person.active ? "활성" : "비활성"}
              </span>
            </div>
            {person.user_id !== session.user_id ? (
              <details>
                <summary>구성원 권한 변경</summary>
                <CommandForm
                  {...schoolForm}
                  path={`/api/school/members/${encodeURIComponent(person.user_id)}`}
                  method="PUT"
                  button="권한 변경 저장"
                >
                  <label>
                    구성원 권한
                    <select name="role" defaultValue={person.role}>
                      <option value="TEACHER">교사</option>
                      <option value="ADMIN">관리자</option>
                    </select>
                  </label>
                  <input type="hidden" name="active" value="false" />
                  <label>
                    <span>
                      <input
                        style={{ width: "auto" }}
                        type="checkbox"
                        name="active"
                        value="true"
                        defaultChecked={!!person.active}
                      />{" "}
                      계정 활성
                    </span>
                  </label>
                  <label>
                    권한 변경 사유
                    <textarea required name="reason" maxLength={10000} />
                  </label>
                </CommandForm>
              </details>
            ) : null}
          </article>
        ))}
      </section>
      <section className="panel">
        <h2>부재와 대체 담당</h2>
        <p className="hint">
          부재 기간의 지원 요청은 같은 역할의 활성 대체자를 먼저 확인합니다.
          대체자가 맡아도 사건 총괄은 유지됩니다.
        </p>
        {config.absences.length === 0 ? (
          <Empty>등록한 부재 설정이 없습니다.</Empty>
        ) : (
          config.absences.map((item) => (
            <article className="work-item" key={item.id}>
              <div className="item-top">
                <strong>
                  {item.user_id} → {item.substitute_id}
                </strong>
                <span className="badge">
                  {item.active ? "설정 활성" : "해제됨"}
                </span>
              </div>
              <p className="meta">
                {date(item.starts_at)} ~ {date(item.ends_at)}
              </p>
              {item.note ? <p>{item.note}</p> : null}
              {item.active ? (
                <details>
                  <summary>부재 설정 해제</summary>
                  <CommandForm
                    {...schoolForm}
                    path={`/api/school/absences/${encodeURIComponent(item.id)}/cancel`}
                    button="부재 설정 해제"
                  >
                    <label>
                      해제 사유
                      <textarea name="reason" required maxLength={10000} />
                    </label>
                  </CommandForm>
                </details>
              ) : null}
            </article>
          ))
        )}
        <details className="new-request">
          <summary>부재·대체자 등록</summary>
          <CommandForm
            {...schoolForm}
            path="/api/school/absences"
            button="부재 일정 저장"
            transformValues={(values) => ({
              ...values,
              starts_at: koreanTime(values.starts_at),
              ends_at: koreanTime(values.ends_at),
            })}
          >
            <div className="form-row">
              <label>
                부재 구성원
                <select
                  name="user_id"
                  required
                  defaultValue=""
                  onChange={(event) => setTarget(event.target.value)}
                >
                  <option value="" disabled>
                    구성원 선택
                  </option>
                  {active.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.user_id} ({label(m.role)})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                대체 구성원
                <select name="substitute_id" required defaultValue="">
                  <option value="" disabled>
                    같은 역할의 구성원 선택
                  </option>
                  {active
                    .filter(
                      (m) => m.role === targetRole && m.user_id !== target,
                    )
                    .map((m) => (
                      <option key={m.user_id}>{m.user_id}</option>
                    ))}
                </select>
              </label>
            </div>
            <div className="form-row">
              <label>
                부재 시작 (한국시간)
                <input type="datetime-local" name="starts_at" required />
              </label>
              <label>
                부재 종료 (한국시간)
                <input type="datetime-local" name="ends_at" required />
              </label>
            </div>
            <label>
              업무 공백 안내
              <textarea name="note" maxLength={10000} />
            </label>
          </CommandForm>
        </details>
      </section>
      <section className="panel">
        <h2>학교 업무분장</h2>
        {config.responsibilities.length === 0 ? (
          <Empty>등록한 업무분장이 없습니다.</Empty>
        ) : (
          config.responsibilities.map((item) => (
            <article className="work-item" key={item.id}>
              <div className="item-top">
                <strong>{item.label}</strong>
                <span className="badge">
                  {item.active ? "사용 중" : "해제됨"}
                </span>
              </div>
              <p>
                담당 {item.user_id} · 대체 {item.substitute_id ?? "미지정"}
              </p>
              {item.active ? (
                <details>
                  <summary>업무분장 해제</summary>
                  <CommandForm
                    {...schoolForm}
                    path={`/api/school/responsibilities/${encodeURIComponent(item.id)}/remove`}
                    button="업무분장 해제"
                  >
                    <label>
                      해제 사유
                      <textarea required name="reason" maxLength={10000} />
                    </label>
                  </CommandForm>
                </details>
              ) : null}
            </article>
          ))
        )}
        <details className="new-request">
          <summary>업무분장 추가</summary>
          <CommandForm
            {...schoolForm}
            path="/api/school/responsibilities"
            button="업무분장 저장"
          >
            <label>
              업무 이름
              <input name="label" required maxLength={128} />
            </label>
            <div className="form-row">
              <label>
                업무 담당
                <select name="user_id" required defaultValue="">
                  <option value="" disabled>
                    구성원 선택
                  </option>
                  {active.map((m) => (
                    <option key={m.user_id}>{m.user_id}</option>
                  ))}
                </select>
              </label>
              <label>
                업무 대체자
                <select name="substitute_id" defaultValue="">
                  <option value="">미지정</option>
                  {active.map((m) => (
                    <option key={m.user_id}>{m.user_id}</option>
                  ))}
                </select>
              </label>
            </div>
          </CommandForm>
        </details>
      </section>
      <section className="panel">
        <h2>앱 수신함 전달 현황</h2>
        <p className="hint">
          최근 100개 알림입니다. 수신함 전달은 사용자의 확인이나 실제 지원 수신
          확인과 다릅니다.
        </p>
        <details>
          <summary>최근 전달 기록 보기</summary>
          {deliveries.isPending ? (
            <p>전달 상태 확인 중…</p>
          ) : deliveries.error ? (
            <ErrorNotice error={deliveries.error} />
          ) : deliveries.data?.length === 0 ? (
            <Empty>전달 기록이 없습니다.</Empty>
          ) : (
            deliveries.data?.map((item) => (
              <article className="work-item" key={item.id}>
                <div className="item-top">
                  <strong>받는 구성원 {item.recipient_id}</strong>
                  <span className="badge">
                    {item.status === "QUEUED"
                      ? "전달 대기"
                      : item.status === "DELIVERED"
                        ? "수신함 전달"
                        : item.status === "ACKNOWLEDGED"
                          ? "알림 확인함"
                          : "전달 실패"}
                  </span>
                </div>
                <p className="meta">
                  사건 {item.case_id} · 전달 시도 {item.attempts}회
                </p>
                {item.error_code ? (
                  <p className="hint">
                    {item.error_code === "RECIPIENT_UNAVAILABLE"
                      ? "활성 구성원 상태를 확인해 주세요."
                      : "사건 접근 권한을 확인해 주세요."}
                  </p>
                ) : null}
                {item.status === "FAILED" ? (
                  <MetadataAction
                    path={`/api/notifications/${encodeURIComponent(item.id)}/retry`}
                  >
                    전달 다시 시도
                  </MetadataAction>
                ) : null}
              </article>
            ))
          )}
        </details>
      </section>
      <SettingsHistory version={config.version} />
    </>
  );
}

export function SchoolContacts() {
  const { api } = useSession();
  const scope = useScope();
  const contacts = useQuery({
    queryKey: ["school-contacts", ...scope],
    queryFn: ({ signal }) =>
      api.get<(Responsibility & { support_contact_id: string | null })[]>(
        "/api/school/contacts",
        signal,
      ),
  });
  return (
    <>
      <h1>학교 지원 담당</h1>
      <p>업무분장과 학교의 지원 담당을 확인하세요.</p>
      <section className="panel">
        {contacts.isPending ? (
          <p>불러오는 중…</p>
        ) : contacts.error ? (
          <ErrorNotice error={contacts.error} />
        ) : contacts.data.length === 0 ? (
          <Empty>학교에서 등록한 업무분장이 없습니다.</Empty>
        ) : (
          contacts.data.map((item) => (
            <article className="work-item" key={item.id}>
              <h2>{item.label}</h2>
              <p>
                담당 {item.user_id} · 대체 {item.substitute_id ?? "미지정"}
              </p>
              <p className="meta">
                지원 연결 관리자 {item.support_contact_id ?? "확인 필요"}
              </p>
            </article>
          ))
        )}
      </section>
    </>
  );
}
