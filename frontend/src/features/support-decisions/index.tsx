import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import type { CaseDetail } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { date, ErrorNotice } from "../../shared/ui";
import type { DocumentVersion } from "../case-comparison";

type Observation = {
  source_id: string;
  kind: "FACT" | "CLAIM" | "UNVERIFIED";
  detail: string;
};
type Decision = {
  decision_id: string;
  revision: number;
  decided_by: string;
  recorded_case_version: number;
  stale: boolean;
  superseded: boolean;
  created_at: string;
  snapshot: {
    decision_type: string;
    reason: string;
    target: string;
    route: string;
    remaining_school_work: string;
    observations: Observation[];
    sources: {
      ref: { resource_type: string; resource_id: string; version: number };
      data: Record<string, unknown>;
    }[];
    remaining_tasks: { id: string; question: string; status: string }[];
    remaining_support: { id: string; reason: string; status: string }[];
    reviewed_ai: { run_id: string; result: { summary: string } } | null;
  };
};
const kinds = {
  FACT: "확인된 사실",
  CLAIM: "당사자 주장",
  UNVERIFIED: "미확인",
};
const types: Record<string, string> = {
  INTERNAL_SUPPORT: "학교 내 지원",
  SPECIALIST_SUPPORT: "전문 지원",
  EXTERNAL_SUPPORT: "외부 지원",
  KEEP_REVIEWING: "추가 검토",
};
type Draft = { key: string; kind: Observation["kind"]; detail: string };

export function SupportDecisions({ record }: { record: CaseDetail }) {
  const { api } = useSession();
  const scope = useScope();
  const list = useQuery({
    queryKey: ["support-decisions", ...scope, record.id, record.version],
    queryFn: ({ signal }) =>
      api.get<Decision[]>(
        `/api/cases/${encodeURIComponent(record.id)}/support-decisions`,
        signal,
      ),
  });
  const files = useQuery({
    queryKey: ["files", ...scope, record.id],
    queryFn: ({ signal }) =>
      api.get<{ id: string; filename: string; category: string }[]>(
        `/api/cases/${encodeURIComponent(record.id)}/files`,
        signal,
      ),
  });
  const runs = useQuery({
    queryKey: ["runs", ...scope, record.id],
    queryFn: ({ signal }) =>
      api.get<
        {
          run_id: string;
          purpose: string;
          status: string;
          reviewed_case_version: number | null;
          input_case_version: number;
        }[]
      >(`/api/cases/${encodeURIComponent(record.id)}/agent-runs`, signal),
  });
  const documents = useQuery({
    queryKey: ["documents", ...scope, record.id, record.version],
    queryFn: ({ signal }) =>
      api.get<DocumentVersion[]>(
        `/api/cases/${encodeURIComponent(record.id)}/documents`,
        signal,
      ),
  });
  const sources = [
    ...(documents.data ?? []).map((item) => ({
      key: `DOCUMENT_VERSION:${item.id}`,
      type: "DOCUMENT_VERSION",
      id: item.id,
      label: `원문: ${item.label} · 버전 ${item.revision}`,
      version: item.revision,
    })),
    {
      key: `CASE:${record.id}`,
      type: "CASE",
      id: record.id,
      label: "사건 기본 정보",
      version: record.version,
    },
    ...record.tasks.map((task) => ({
      key: `TASK:${task.id}`,
      type: "TASK",
      id: task.id,
      label: `업무: ${task.question.slice(0, 70)}`,
      version: record.version,
    })),
    ...record.support_requests.map((item) => ({
      key: `SUPPORT_REQUEST:${item.id}`,
      type: "SUPPORT_REQUEST",
      id: item.id,
      label: `지원: ${item.reason.slice(0, 70)}`,
      version: record.version,
    })),
    ...(files.data ?? [])
      .filter((file) => file.category !== "AUDIO")
      .map((file) => ({
        key: `FILE:${file.id}`,
        type: "FILE",
        id: file.id,
        label: `자료: ${file.filename}`,
        version: 1,
      })),
  ];
  const initial = (): Draft[] => [
    { key: `CASE:${record.id}`, kind: "UNVERIFIED", detail: "" },
  ];
  const [observations, setObservations] = useState<Draft[]>(initial);
  const selected = sources.filter((source) =>
    observations.some((item) => item.key === source.key),
  );
  const latest = list.data?.[0];
  const update = (index: number, values: Partial<Draft>) =>
    setObservations((items) =>
      items.map((item, position) =>
        position === index ? { ...item, ...values } : item,
      ),
    );
  return (
    <>
      <h2>학교의 지원 판단</h2>
      <p>
        기록을 대조하고 사람이 결정합니다. 반복 횟수나 감정만으로 외부 지원을
        정하지 않습니다.
      </p>
      <div className="notice">
        판단 저장은 기관 제출·지원 배정·사건 종결이 아닙니다. 남은 학교 업무는
        교사 업무와 학교 지원에서 계속 처리하세요.
      </div>
      {list.error ? <ErrorNotice error={list.error} /> : null}
      {files.error ? <ErrorNotice error={files.error} /> : null}
      {documents.error ? <ErrorNotice error={documents.error} /> : null}
      {runs.error ? <ErrorNotice error={runs.error} /> : null}
      {record.status !== "CLOSED" && list.data ? (
        <details open={!latest}>
          <summary>
            {latest ? "검토 후 새 판단 기록" : "첫 지원 판단 기록"}
          </summary>
          <CommandForm
            caseId={record.id}
            version={record.version}
            path={`/api/cases/${encodeURIComponent(record.id)}/support-decisions`}
            button="지원 판단 저장"
            onSaved={() => setObservations(initial())}
            transformValues={(values) => ({
              ...values,
              input_refs: JSON.parse(String(values.input_refs)),
              observations: JSON.parse(String(values.observations)),
            })}
          >
            <input
              type="hidden"
              name="supersedes_id"
              value={latest?.decision_id ?? ""}
            />
            <input
              type="hidden"
              name="input_refs"
              value={JSON.stringify(
                selected.map((source) => ({
                  resource_type: source.type,
                  resource_id: source.id,
                  version: source.version,
                })),
              )}
            />
            <input
              type="hidden"
              name="observations"
              value={JSON.stringify(
                observations.map((item) => ({
                  source_id:
                    sources.find((source) => source.key === item.key)?.id ?? "",
                  kind: item.kind,
                  detail: item.detail,
                })),
              )}
            />
            <label>
              지원 방향
              <select name="decision_type" required>
                <option value="KEEP_REVIEWING">추가 검토</option>
                <option value="INTERNAL_SUPPORT">학교 내 지원</option>
                <option value="SPECIALIST_SUPPORT">전문 지원</option>
                <option value="EXTERNAL_SUPPORT">외부 지원</option>
              </select>
            </label>
            <label>
              판단 사유·변경 사유
              <textarea name="reason" required maxLength={10000} />
            </label>
            <label>
              지원 대상
              <textarea name="target" required maxLength={10000} />
            </label>
            <label>
              지원 경로·담당 역할
              <textarea name="route" required maxLength={10000} />
            </label>
            <label>
              남은 학교 업무
              <textarea
                name="remaining_school_work"
                required
                maxLength={10000}
              />
            </label>
            <fieldset>
              <legend>출처를 대조한 관찰</legend>
              {observations.map((item, index) => (
                <fieldset key={index}>
                  <legend>관찰 {index + 1}</legend>
                  <label>
                    출처
                    <select
                      aria-label={`관찰 ${index + 1} 출처`}
                      value={item.key}
                      onChange={(event) =>
                        update(index, { key: event.target.value })
                      }
                      required
                    >
                      {sources.map((source) => (
                        <option key={source.key} value={source.key}>
                          {source.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    구분
                    <select
                      aria-label={`관찰 ${index + 1} 구분`}
                      value={item.kind}
                      onChange={(event) =>
                        update(index, {
                          kind: event.target.value as Draft["kind"],
                        })
                      }
                    >
                      {Object.entries(kinds).map(([key, value]) => (
                        <option key={key} value={key}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    내용
                    <textarea
                      aria-label={`관찰 ${index + 1} 내용`}
                      value={item.detail}
                      onChange={(event) =>
                        update(index, { detail: event.target.value })
                      }
                      required
                      maxLength={10000}
                    />
                  </label>
                  {observations.length > 1 ? (
                    <button
                      type="button"
                      onClick={() =>
                        setObservations((items) =>
                          items.filter((_, position) => index !== position),
                        )
                      }
                    >
                      관찰 {index + 1} 삭제
                    </button>
                  ) : null}
                </fieldset>
              ))}
              <button
                type="button"
                disabled={observations.length >= 20}
                onClick={() =>
                  setObservations((items) => [...items, initial()[0]])
                }
              >
                관찰 추가
              </button>
            </fieldset>
            <label>
              참고한 AI 검토 (선택)
              <select name="reviewed_run_id">
                <option value="">사람이 직접 검토</option>
                {runs.data
                  ?.filter(
                    (run) =>
                      run.purpose === "REVIEW_SUPPORT" &&
                      run.status === "SUCCEEDED" &&
                      (run.reviewed_case_version ?? run.input_case_version) ===
                        record.version,
                  )
                  .map((run) => (
                    <option key={run.run_id} value={run.run_id}>
                      {run.run_id}
                    </option>
                  ))}
              </select>
            </label>
          </CommandForm>
        </details>
      ) : record.status === "CLOSED" ? (
        <p>새 판단은 사건을 재개한 뒤 기록하세요.</p>
      ) : (
        <p>판단 이력을 불러오는 중…</p>
      )}
      <h3>판단 이력</h3>
      {list.data?.length === 0 ? (
        <p>아직 사람이 기록한 지원 판단이 없습니다.</p>
      ) : null}
      {list.data?.map((decision) => (
        <article className="panel" key={decision.decision_id}>
          <h3>
            {types[decision.snapshot.decision_type]} · 판단 {decision.revision}
          </h3>
          <p className="meta">
            {decision.decided_by} · {date(decision.created_at)}
          </p>
          {decision.stale ? (
            <p className="notice">
              {decision.superseded
                ? "이후 새 판단이 기록되었습니다."
                : "이 판단 이후 사건이 변경되었습니다."}{" "}
              보고서에는 현재 기록을 검토한 새 판단을 사용하세요.
            </p>
          ) : (
            <p>현재 사건과 일치하는 최신 판단입니다.</p>
          )}
          <p style={{ whiteSpace: "pre-wrap" }}>{decision.snapshot.reason}</p>
          <dl>
            <dt>대상</dt>
            <dd>{decision.snapshot.target}</dd>
            <dt>경로·역할</dt>
            <dd>{decision.snapshot.route}</dd>
            <dt>남은 학교 업무</dt>
            <dd>{decision.snapshot.remaining_school_work}</dd>
          </dl>
          <ul>
            {decision.snapshot.observations.map((item, index) => (
              <li key={index}>
                <strong>{kinds[item.kind]}</strong>: {item.detail}{" "}
                <small>출처 {item.source_id}</small>
              </li>
            ))}
          </ul>
          <p>
            기록 당시 미완료 업무 {decision.snapshot.remaining_tasks.length}건 ·
            지원 {decision.snapshot.remaining_support.length}건
          </p>
          <details>
            <summary>기록 당시 자료·업무 확인</summary>
            <ul>
              {decision.snapshot.sources.map((source) => (
                <li
                  key={`${source.ref.resource_type}:${source.ref.resource_id}`}
                >
                  {source.ref.resource_type} · {source.ref.resource_id} · 기록
                  버전 {source.ref.version}
                  <pre
                    style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                  >
                    {String(
                      source.data.content ??
                        source.data.text ??
                        source.data.reply ??
                        source.data.question ??
                        source.data.reason ??
                        source.data.title ??
                        source.data.filename ??
                        "",
                    )}
                  </pre>
                </li>
              ))}
            </ul>
            <ul>
              {decision.snapshot.remaining_tasks.map((task) => (
                <li key={task.id}>
                  {task.question} · {task.status}
                </li>
              ))}
            </ul>
            <ul>
              {decision.snapshot.remaining_support.map((item) => (
                <li key={item.id}>
                  {item.reason} · {item.status}
                </li>
              ))}
            </ul>
          </details>
          {decision.snapshot.reviewed_ai ? (
            <p>
              검토 완료 AI 참고: {decision.snapshot.reviewed_ai.result.summary}
            </p>
          ) : (
            <p>사람이 직접 검토한 판단입니다.</p>
          )}
          <p className="meta">
            보고서 참조 ID {decision.decision_id} · 사건 버전{" "}
            {decision.recorded_case_version}
          </p>
        </article>
      ))}
    </>
  );
}
