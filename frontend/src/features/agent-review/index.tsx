import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import { ApiError, command, type Command } from "../../lib/api/client";
import type { CaseDetail } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { Badge, date, Empty, ErrorNotice, label } from "../../shared/ui";
import type { DocumentVersion } from "../case-comparison";

type Review = {
  summary: string;
  observations: { source_id: string; kind: string; detail: string }[];
  missing_information: string[];
  suggested_support: string;
  action_options: string[];
  response_draft: string;
  validation_checks: string[];
  evidence_used: string[];
  translated_response?: {
    target_language: string;
    translated_text: string;
    translation_mode: string;
  } | null;
};
type Run = {
  run_id: string;
  purpose: string;
  status: string;
  step: string;
  result: Review | null;
  error: { code: string; message: string; retryable: boolean } | null;
  generation_mode: string;
  input_case_version: number;
  reviewed_case_version: number | null;
  stale: boolean;
  attempts: number;
  created_at: string;
};

export function AgentReview({ record }: { record: CaseDetail }) {
  const { api, session } = useSession();
  const scope = useScope();
  const queries = useQueryClient();
  const [failed, setFailed] = useState<Command | null>(null);
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);
  const documents = useQuery({
    queryKey: ["documents", ...scope, record.id, record.version],
    enabled: session.role === "ADMIN",
    queryFn: ({ signal }) =>
      api.get<DocumentVersion[]>(
        `/api/cases/${encodeURIComponent(record.id)}/documents`,
        signal,
      ),
  });
  const capabilities = useQuery({
    queryKey: ["agent-capabilities", ...scope],
    queryFn: ({ signal }) =>
      api.get<{ purpose: string; generation_mode: string }[]>(
        "/api/agent-capabilities",
        signal,
      ),
  });
  const runs = useQuery({
    queryKey: ["runs", ...scope, record.id],
    queryFn: ({ signal }) =>
      api.get<Run[]>(
        `/api/cases/${encodeURIComponent(record.id)}/agent-runs`,
        signal,
      ),
    refetchInterval: (query) =>
      query.state.data?.some(
        (run) =>
          run.purpose === "REVIEW_SUPPORT" &&
          ["QUEUED", "RUNNING"].includes(run.status),
      )
        ? 1500
        : false,
  });
  const start = useMutation({
    mutationFn: (cmd: Command) => api.execute(cmd),
    onSuccess: async () => {
      setFailed(null);
      await queries.invalidateQueries({
        queryKey: ["runs", ...scope, record.id],
      });
    },
    onError: async (error, cmd) => {
      setFailed(cmd);
      if (error instanceof ApiError && error.status === 409)
        await queries.invalidateQueries({
          queryKey: ["case", ...scope, record.id],
        });
    },
  });
  const supportRuns =
    runs.data?.filter((run) => run.purpose === "REVIEW_SUPPORT") ?? [];
  const available = capabilities.data?.some(
    (c) => c.purpose === "REVIEW_SUPPORT",
  );
  const request = (retryOf?: string) => {
    const selected = (documents.data ?? [])
      .filter((item) => selectedDocuments.includes(item.id))
      .map((item) => ({
        resource_type: "DOCUMENT_VERSION",
        resource_id: item.id,
        version: item.revision,
      }));
    const input_refs = [
      {
        resource_type: "CASE",
        resource_id: record.id,
        version: record.version,
      },
      ...selected,
      ...record.tasks.slice(-10).map((t) => ({
        resource_type: "TASK",
        resource_id: t.id,
        version: record.version,
      })),
      ...record.support_requests.slice(-9).map((s) => ({
        resource_type: "SUPPORT_REQUEST",
        resource_id: s.id,
        version: record.version,
      })),
    ].slice(0, 20);
    start.mutate(
      command(`/api/cases/${encodeURIComponent(record.id)}/agent-runs`, {
        expected_version: record.version,
        purpose: "REVIEW_SUPPORT",
        input_refs,
        ...(retryOf ? { retry_of_run_id: retryOf } : {}),
      }),
    );
  };
  return (
    <>
      <h2>함께 검토할 지원 방향</h2>
      <p className="hint">
        현재 민원과 업무·지원 기록을 바탕으로 다음 행동을 제안합니다. AI 제안은
        총괄·지원 결정이나 답변 승인으로 자동 반영되지 않습니다. 첨부 원문은
        자동 포함하지 않습니다.
      </p>
      {capabilities.error ? (
        <ErrorNotice error={capabilities.error} />
      ) : !capabilities.isPending && !available ? (
        <div className="notice">
          OpenAI 연결 설정이 준비되지 않았습니다. 학교 업무·지원 요청은 계속
          사용할 수 있습니다.
        </div>
      ) : null}
      {record.tasks.length > 10 || record.support_requests.length > 9 ? (
        <p className="notice">
          한 번에 업무 10건·지원 9건까지 포함합니다. 전체 기록은 민원 탭에서
          함께 대조해 주세요.
        </p>
      ) : null}
      {session.role === "ADMIN" && documents.data?.length ? (
        <details>
          <summary>함께 검토할 원문 버전 선택</summary>
          <p>
            선택한 버전만 AI에 포함합니다. 민원 포함 최대 20개 출처이며 원문
            선택 시 업무·지원 기록 일부가 제외될 수 있습니다.
          </p>
          {documents.data.map((item) => (
            <label key={item.id}>
              <input
                type="checkbox"
                checked={selectedDocuments.includes(item.id)}
                disabled={
                  start.isPending ||
                  !!failed ||
                  (!selectedDocuments.includes(item.id) &&
                    selectedDocuments.length >= 10)
                }
                onChange={(event) =>
                  setSelectedDocuments((ids) =>
                    event.target.checked
                      ? [...ids, item.id]
                      : ids.filter((id) => id !== item.id),
                  )
                }
              />
              {item.label} · 버전 {item.revision}
            </label>
          ))}
        </details>
      ) : null}
      {documents.error ? <ErrorNotice error={documents.error} /> : null}
      <button
        className="primary"
        disabled={
          !available ||
          record.status === "CLOSED" ||
          start.isPending ||
          !!failed
        }
        onClick={() => request()}
      >
        {start.isPending ? "요청 저장 중…" : "AI 지원 검토 시작"}
      </button>
      {start.error ? (
        <ErrorNotice error={start.error}>
          {start.error instanceof ApiError && start.error.uncertain ? (
            <button
              disabled={start.isPending}
              onClick={() => failed && start.mutate(failed)}
            >
              같은 생성 요청 다시 확인
            </button>
          ) : (
            <button
              onClick={() => {
                setFailed(null);
                start.reset();
              }}
            >
              내용 확인 후 다시 요청
            </button>
          )}
        </ErrorNotice>
      ) : null}
      {runs.isPending ? (
        <p>실행 상태를 확인하는 중…</p>
      ) : runs.error ? (
        <ErrorNotice error={runs.error} />
      ) : supportRuns.length === 0 ? (
        <Empty>아직 생성한 지원 검토가 없습니다.</Empty>
      ) : (
        supportRuns.map((run) => (
          <article className="work-item" key={run.run_id}>
            <div className="item-top">
              <strong>지원 검토</strong>
              <Badge value={run.status} />
            </div>
            <p className="meta">
              {date(run.created_at)} ·{" "}
              {run.generation_mode === "MODEL"
                ? "모델 생성"
                : run.generation_mode === "RULE"
                  ? "규칙 검토"
                  : "수동 기록"}{" "}
              · 시도 {run.attempts}회
            </p>
            {run.stale ? (
              <div className="notice">
                생성에 사용한 기록 이후 민원이 변경되었습니다. 최신 민원과
                대조해 주세요.
              </div>
            ) : null}
            {["QUEUED", "RUNNING"].includes(run.status) ? (
              <p role="status">
                {run.step === "retry_wait"
                  ? "공급자 응답을 기다린 뒤 다시 시도합니다."
                  : "검토를 준비하고 있습니다. 화면을 나갔다 돌아와도 실행 상태를 확인할 수 있습니다."}
              </p>
            ) : null}
            {run.error ? (
              <div className="notice error" role="alert">
                {run.error.message}
              </div>
            ) : null}
            {run.result ? (
              <>
                <p className="preserve">{run.result.summary}</p>
                <h3>기록과 확인할 점</h3>
                <ul>
                  {run.result.observations.map((o, i) => (
                    <li key={i}>
                      <strong>
                        {o.kind === "FACT"
                          ? "기록상 사실"
                          : o.kind === "CLAIM"
                            ? "당사자 주장"
                            : "미확인"}
                      </strong>{" "}
                      · {o.detail}
                      <small>출처 {o.source_id}</small>
                    </li>
                  ))}
                </ul>
                {run.result.missing_information.length ? (
                  <>
                    <h3>추가로 확인할 정보</h3>
                    <ul>
                      {run.result.missing_information.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ul>
                  </>
                ) : null}
                <h3>제안하는 지원 방향</h3>
                <p>{label(run.result.suggested_support)}</p>
                <h3>검토할 행동</h3>
                <ul>
                  {run.result.action_options.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
                <h3>AI가 준비한 보호자 답변</h3>
                <p className="preserve">{run.result.response_draft}</p>
                {run.result.translated_response ? (
                  <>
                    <h3>원문 언어 답변</h3>
                    <p className="preserve">
                      {run.result.translated_response.translated_text}
                    </p>
                  </>
                ) : null}
                <h3>Validator 점검</h3>
                <ul>
                  {run.result.validation_checks.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
                <p className="hint">
                  사용한 공식 근거:{" "}
                  {run.result.evidence_used.join(", ") || "직접 인용 근거 없음"}{" "}
                  · 관리자 검토 전에는 발송되지 않습니다.
                </p>
              </>
            ) : null}
            {record.status === "OPEN" &&
            (run.status === "WAITING_REVIEW" ||
              (run.status === "SUCCEEDED" &&
                run.reviewed_case_version !== record.version)) ? (
              <CommandForm
                caseId={record.id}
                version={record.version}
                path={`/api/agent-runs/${encodeURIComponent(run.run_id)}/review`}
                button="원문 대조 후 검토 완료"
              >
                <input type="hidden" name="decision" value="ACCEPT" />
                <label>
                  검토 내용
                  <textarea name="reason" required maxLength={10000} />
                </label>
                {run.stale ? (
                  <label>
                    <span>
                      <input
                        style={{ width: "auto" }}
                        name="accept_stale"
                        type="checkbox"
                        value="true"
                        required
                      />{" "}
                      변경된 민원과 이 결과를 다시 대조했습니다.
                    </span>
                  </label>
                ) : null}
              </CommandForm>
            ) : null}
            {["QUEUED", "RUNNING", "WAITING_REVIEW"].includes(run.status) ? (
              <details className="new-request">
                <summary>이 실행 취소</summary>
                <CommandForm
                  caseId={record.id}
                  version={record.version}
                  path={`/api/agent-runs/${encodeURIComponent(run.run_id)}/cancel`}
                  button="생성·검토 취소"
                >
                  <label>
                    취소 사유
                    <textarea name="reason" required maxLength={10000} />
                  </label>
                </CommandForm>
              </details>
            ) : null}
            {record.status === "OPEN" &&
            ["FAILED", "CANCELLED"].includes(run.status) ? (
              <button
                disabled={!available || start.isPending || !!failed}
                onClick={() => request(run.run_id)}
              >
                최신 기록으로 다시 생성
              </button>
            ) : null}
          </article>
        ))
      )}
    </>
  );
}
