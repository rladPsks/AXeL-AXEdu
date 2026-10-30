import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import { command, type Command } from "../../lib/api/client";
import type { CaseDetail } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { date, ErrorNotice, label } from "../../shared/ui";
import type { PairEvidence } from "./index";

type Source = {
  ref: { resource_type: string; resource_id: string; version: number };
  data: Record<string, unknown>;
};
type Input = {
  id: string;
  case_id: string;
  related_case_id: string;
  case_version: number;
  related_case_version: number;
  stale: boolean;
  sources: Source[];
  created_at: string;
};
type Finding = {
  category: string;
  assessment: string;
  detail: string;
  source_ids: string[];
};
export type ComparisonReview = {
  id: string;
  revision: number;
  related_case_id: string;
  recorded_by: string;
  recorded_case_version: number;
  stale: boolean;
  reason: string;
  findings: Finding[];
  input: Input;
  created_at: string;
};
type Result = {
  summary: string;
  findings: Finding[];
  missing_information: string[];
  follow_up_questions: string[];
};
type Run = {
  run_id: string;
  purpose: string;
  status: string;
  stale: boolean;
  generation_mode: string;
  result: Result | null;
  error: { message: string } | null;
  input_refs: { resource_type: string; resource_id: string }[];
  reviewed_case_version: number | null;
};
const categories: Record<string, string> = {
  NEW_FACT: "새롭게 기록된 사실 관련 내용",
  NEW_EVIDENCE: "새 증거",
  UNANSWERED_FOLLOWUP: "미응답 재문의 관련 기록",
  UNFULFILLED_ACTION: "미이행 조치 관련 기록",
  REPEATED_CONTENT: "반복된 내용",
  REPORTING_LANGUAGE: "신고 표현",
  NEEDS_CONFIRMATION: "추가 확인 필요",
};
const assessments: Record<string, string> = {
  FACT: "확인된 사실",
  CLAIM: "당사자 주장",
  UNVERIFIED: "미확인",
};

export function ComparisonReviewPanel({
  record,
  pair,
  ready = true,
}: {
  record: CaseDetail;
  pair: { current: PairEvidence; related: PairEvidence };
  ready?: boolean;
}) {
  const { api } = useSession();
  const scope = useScope();
  const queries = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const [inputId, setInputId] = useState<string | null>(null);
  const [failed, setFailed] = useState<Command | null>(null);
  const initial = (): Finding[] => [
    {
      category: "NEEDS_CONFIRMATION",
      assessment: "UNVERIFIED",
      detail: "",
      source_ids: [record.id],
    },
  ];
  const [findings, setFindings] = useState<Finding[]>(initial);
  const inputs = useQuery<Input[]>({
    placeholderData: (previous) => previous,
    queryKey: [
      "comparison-inputs",
      ...scope,
      record.id,
      record.version,
      pair.related.case.version,
    ],
    queryFn: ({ signal }) =>
      api.get<Input[]>(
        `/api/cases/${encodeURIComponent(record.id)}/comparison-inputs`,
        signal,
      ),
  });
  const reviews = useQuery<ComparisonReview[]>({
    placeholderData: (previous) => previous,
    queryKey: [
      "comparison-reviews",
      ...scope,
      record.id,
      record.version,
      pair.related.case.version,
    ],
    queryFn: ({ signal }) =>
      api.get<ComparisonReview[]>(
        `/api/cases/${encodeURIComponent(record.id)}/comparison-reviews`,
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
          run.purpose === "COMPARE_CASES" &&
          ["QUEUED", "RUNNING"].includes(run.status),
      )
        ? 1500
        : false,
  });
  const capabilities = useQuery({
    queryKey: ["agent-capabilities", ...scope],
    queryFn: ({ signal }) =>
      api.get<{ purpose: string }[]>("/api/agent-capabilities", signal),
  });
  const refresh = () =>
    Promise.all([
      queries.invalidateQueries({ queryKey: ["case", ...scope, record.id] }),
      queries.invalidateQueries({ queryKey: ["comparison-pair", ...scope] }),
      queries.invalidateQueries({ queryKey: ["comparison-inputs", ...scope] }),
      queries.invalidateQueries({ queryKey: ["comparison-reviews", ...scope] }),
      queries.invalidateQueries({ queryKey: ["runs", ...scope, record.id] }),
    ]);
  const action = useMutation({
    mutationFn: (cmd: Command) =>
      api.execute<{ comparison_input_id?: string }>(cmd),
    onSuccess: async (result) => {
      setFailed(null);
      if (result.comparison_input_id) setInputId(result.comparison_input_id);
      await refresh();
    },
    onError: (error, cmd) => {
      setFailed(cmd);
      void refresh();
    },
  });
  const savedInputs = (inputs.data ?? []).filter(
    (input) => input.related_case_id === pair.related.case.id,
  );
  const input = savedInputs.find(
    (item) => item.id === (inputId ?? savedInputs[0]?.id),
  );
  useEffect(() => {
    if (inputId === null && savedInputs.length) setInputId(savedInputs[0].id);
  }, [inputId, savedInputs]);
  const latest = reviews.data?.find(
    (item) => item.related_case_id === pair.related.case.id,
  );
  const available = capabilities.data?.some(
    (item) => item.purpose === "COMPARE_CASES",
  );
  const sourceOptions = [pair.current, pair.related].flatMap((side) => [
    ...side.documents.map((item) => ({
      key: `DOCUMENT_VERSION:${item.id}`,
      case_id: side.case.id,
      resource_type: "DOCUMENT_VERSION",
      resource_id: item.id,
      version: item.revision,
      label: `${side.case.id} · ${item.label} · 버전 ${item.revision}`,
    })),
    ...side.tasks.map((item) => ({
      key: `TASK:${item.id}`,
      case_id: side.case.id,
      resource_type: "TASK",
      resource_id: item.id,
      version: side.case.version,
      label: `${side.case.id} · 업무: ${item.question.slice(0, 70)}`,
    })),
    ...side.support_requests.map((item) => ({
      key: `SUPPORT_REQUEST:${item.id}`,
      case_id: side.case.id,
      resource_type: "SUPPORT_REQUEST",
      resource_id: item.id,
      version: side.case.version,
      label: `${side.case.id} · 지원: ${item.reason.slice(0, 70)}`,
    })),
  ]);
  const relatedRuns = (runs.data ?? []).filter(
    (run) =>
      run.purpose === "COMPARE_CASES" &&
      run.input_refs.some(
        (ref) =>
          ref.resource_type === "COMPARISON_INPUT" &&
          ref.resource_id === input?.id,
      ),
  );
  const update = (index: number, values: Partial<Finding>) =>
    setFindings((items) =>
      items.map((item, position) =>
        position === index ? { ...item, ...values } : item,
      ),
    );
  const sourceLabel = (source: Source) =>
    `${String(source.data.label ?? source.data.question ?? source.data.reason ?? source.data.title ?? source.ref.resource_id).slice(0, 90)} · ${String(source.data.case_id ?? source.data.id ?? "")} · 버전 ${source.ref.version}`;
  const start = (retry?: string) =>
    input &&
    action.mutate(
      command(`/api/cases/${encodeURIComponent(record.id)}/agent-runs`, {
        expected_version: record.version,
        purpose: "COMPARE_CASES",
        input_refs: [
          {
            resource_type: "COMPARISON_INPUT",
            resource_id: input.id,
            version: 1,
          },
        ],
        ...(retry ? { retry_of_run_id: retry } : {}),
      }),
    );
  return (
    <section className="panel comparison-review">
      <h3>두 사건의 비교 검토 기록</h3>
      <p>
        선택한 자료를 고정해 대조합니다. AI 없이도 사람이 검토 결과를 기록할 수
        있습니다.
      </p>
      <details>
        <summary>비교할 원문·업무 선택</summary>
        <p>
          두 사건의 기본 정보와 아래에서 선택한 자료만 비교에 포함합니다. 최대
          18개를 선택할 수 있습니다.
        </p>
        {sourceOptions.map((source) => (
          <label key={source.key}>
            <input
              type="checkbox"
              checked={selected.includes(source.key)}
              disabled={
                action.isPending ||
                !!failed ||
                (!selected.includes(source.key) && selected.length >= 18)
              }
              onChange={(event) =>
                setSelected((items) =>
                  event.target.checked
                    ? [...items, source.key]
                    : items.filter((item) => item !== source.key),
                )
              }
            />
            {source.label}
          </label>
        ))}
      </details>
      <button
        disabled={
          !ready || record.status === "CLOSED" || action.isPending || !!failed
        }
        onClick={() =>
          action.mutate(
            command(
              `/api/cases/${encodeURIComponent(record.id)}/comparison-inputs`,
              {
                expected_version: record.version,
                related_case_id: pair.related.case.id,
                expected_related_version: pair.related.case.version,
                source_refs: [
                  ...[pair.current, pair.related].map((side) => ({
                    case_id: side.case.id,
                    resource_type: "CASE",
                    resource_id: side.case.id,
                    version:
                      side.case.id === record.id
                        ? record.version
                        : side.case.version,
                  })),
                  ...sourceOptions
                    .filter((source) => selected.includes(source.key))
                    .map(({ key, label, ...ref }) => ref),
                ],
              },
            ),
          )
        }
      >
        선택한 자료로 비교 준비
      </button>
      {action.error ? (
        <ErrorNotice error={action.error}>
          <button
            disabled={action.isPending}
            onClick={() => failed && action.mutate(failed)}
          >
            같은 요청 다시 확인
          </button>
          <button
            onClick={() => {
              setFailed(null);
              action.reset();
            }}
          >
            최신 자료 확인 후 다시 준비
          </button>
        </ErrorNotice>
      ) : null}
      {inputs.error ? <ErrorNotice error={inputs.error} /> : null}
      {reviews.error ? <ErrorNotice error={reviews.error} /> : null}
      {runs.error ? <ErrorNotice error={runs.error} /> : null}
      {capabilities.error ? <ErrorNotice error={capabilities.error} /> : null}
      <label>
        저장한 비교 자료
        <select
          value={inputId ?? savedInputs[0]?.id ?? ""}
          onChange={(event) => {
            setInputId(event.target.value);
            setFindings(initial());
          }}
        >
          <option value="">비교 자료를 준비하거나 선택하세요</option>
          {savedInputs.map((item) => (
            <option key={item.id} value={item.id}>
              {date(item.created_at)} ·{" "}
              {item.stale ? "재준비 필요" : "현재 자료"} · {item.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      {input?.stale ? (
        <p className="notice">
          이 비교 입력은 이전 사건 버전을 담고 있습니다. 새 검토에는 현재 자료로
          비교를 다시 준비하세요.
        </p>
      ) : null}
      {input && !input.stale ? (
        <>
          <button
            disabled={
              !available ||
              action.isPending ||
              !!failed ||
              record.status === "CLOSED"
            }
            onClick={() => start()}
          >
            AI 사건 비교 시작
          </button>
          {!available ? (
            <p>
              OpenAI 비교 기능이 준비되지 않았습니다. 사람의 검토 기록은 계속
              사용할 수 있습니다.
            </p>
          ) : null}
        </>
      ) : null}
      {relatedRuns.map((run) => (
        <article className="work-item" key={run.run_id}>
          <h4>AI 비교 제안 · {label(run.status)}</h4>
          <p>
            {run.generation_mode === "MODEL"
              ? "모델 생성 제안"
              : "규칙/검증용 결과 — 실제 모델 호출 아님"}
          </p>
          {run.stale ? (
            <p className="notice">
              사건 또는 기준이 바뀐 과거 결과입니다. 새 비교 자료로 다시
              검토하세요.
            </p>
          ) : null}
          {run.error ? <p role="alert">{run.error.message}</p> : null}
          {run.result ? (
            <>
              <p>{run.result.summary}</p>
              <ul>
                {run.result.findings.map((finding, index) => (
                  <li key={index}>
                    {categories[finding.category]} ·{" "}
                    {assessments[finding.assessment]}: {finding.detail}
                    <small> 출처 {finding.source_ids.join(", ")}</small>
                  </li>
                ))}
              </ul>
              <p>부족한 정보: {run.result.missing_information.join(" / ")}</p>
              <p>다음 확인: {run.result.follow_up_questions.join(" / ")}</p>
            </>
          ) : null}
          {run.status === "WAITING_REVIEW" && !run.stale ? (
            <CommandForm
              caseId={record.id}
              version={record.version}
              path={`/api/agent-runs/${encodeURIComponent(run.run_id)}/review`}
              button="AI 제안 검토 기록"
            >
              <label>
                AI 제안 검토
                <select name="decision">
                  <option value="ACCEPT">제안을 검토함</option>
                  <option value="REJECT">제안을 사용하지 않음</option>
                </select>
              </label>
              <label>
                AI 검토 사유
                <textarea name="reason" required maxLength={10000} />
              </label>
            </CommandForm>
          ) : null}
          {["QUEUED", "RUNNING", "WAITING_REVIEW"].includes(run.status) ? (
            <details>
              <summary>AI 비교 취소</summary>
              <CommandForm
                caseId={record.id}
                version={record.version}
                path={`/api/agent-runs/${encodeURIComponent(run.run_id)}/cancel`}
                button="AI 비교 취소"
              >
                <label>
                  취소 사유
                  <textarea name="reason" required maxLength={10000} />
                </label>
              </CommandForm>
            </details>
          ) : null}
          {["FAILED", "CANCELLED"].includes(run.status) &&
          input &&
          !input.stale ? (
            <button
              disabled={action.isPending || !!failed}
              onClick={() => start(run.run_id)}
            >
              AI 비교 재실행
            </button>
          ) : null}
          {run.status === "SUCCEEDED" && !run.stale && run.result ? (
            <button
              onClick={() =>
                setFindings(
                  run.result!.findings.length
                    ? run.result!.findings
                    : initial(),
                )
              }
            >
              검토한 AI 관찰을 사람 기록에 불러오기
            </button>
          ) : null}
        </article>
      ))}
      {input && reviews.data ? (
        <details open>
          <summary>사람이 비교 검토 기록</summary>
          <CommandForm
            caseId={record.id}
            version={record.version}
            path={`/api/cases/${encodeURIComponent(record.id)}/comparison-reviews`}
            button="사람의 비교 검토 저장"
            disabled={
              !ready ||
              input.stale ||
              inputs.isFetching ||
              reviews.isFetching ||
              record.status === "CLOSED"
            }
            onSaved={() => setFindings(initial())}
            transformValues={(values) => ({
              ...values,
              findings: JSON.parse(String(values.findings)),
            })}
          >
            <input type="hidden" name="input_id" value={input.id} />
            <input
              type="hidden"
              name="supersedes_id"
              value={latest?.id ?? ""}
            />
            <input
              type="hidden"
              name="findings"
              value={JSON.stringify(findings)}
            />
            <label>
              비교 검토 사유
              <textarea name="reason" required maxLength={10000} />
            </label>
            {findings.map((finding, index) => (
              <fieldset key={index}>
                <legend>비교 관찰 {index + 1}</legend>
                <label>
                  관찰 구분
                  <select
                    aria-label={`비교 관찰 ${index + 1} 구분`}
                    value={finding.category}
                    onChange={(event) =>
                      update(index, { category: event.target.value })
                    }
                  >
                    {Object.entries(categories).map(([key, value]) => (
                      <option key={key} value={key}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  확인 수준
                  <select
                    aria-label={`비교 관찰 ${index + 1} 확인 수준`}
                    value={finding.assessment}
                    onChange={(event) =>
                      update(index, { assessment: event.target.value })
                    }
                  >
                    {Object.entries(assessments).map(([key, value]) => (
                      <option key={key} value={key}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  비교 관찰 내용
                  <textarea
                    aria-label={`비교 관찰 ${index + 1} 내용`}
                    value={finding.detail}
                    onChange={(event) =>
                      update(index, { detail: event.target.value })
                    }
                    required
                    maxLength={10000}
                  />
                </label>
                <label>
                  관찰 출처 (복수 선택 가능)
                  <select
                    multiple
                    aria-label={`비교 관찰 ${index + 1} 출처`}
                    value={finding.source_ids}
                    required
                    onChange={(event) =>
                      update(index, {
                        source_ids: [...event.target.selectedOptions].map(
                          (option) => option.value,
                        ),
                      })
                    }
                  >
                    {input.sources.map((source) => (
                      <option
                        key={`${source.ref.resource_type}:${source.ref.resource_id}`}
                        value={source.ref.resource_id}
                      >
                        {sourceLabel(source)}
                      </option>
                    ))}
                  </select>
                </label>
                {findings.length > 1 ? (
                  <button
                    type="button"
                    onClick={() =>
                      setFindings((items) =>
                        items.filter((_, position) => position !== index),
                      )
                    }
                  >
                    비교 관찰 {index + 1} 삭제
                  </button>
                ) : null}
              </fieldset>
            ))}
            <button
              type="button"
              disabled={findings.length >= 20}
              onClick={() => setFindings((items) => [...items, initial()[0]])}
            >
              비교 관찰 추가
            </button>
            <label>
              참고한 검토 완료 AI (선택)
              <select name="reviewed_run_id">
                <option value="">사람이 직접 대조</option>
                {relatedRuns
                  .filter(
                    (run) =>
                      run.status === "SUCCEEDED" &&
                      !run.stale &&
                      run.reviewed_case_version === record.version,
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
      ) : null}
      <h4>사람의 비교 검토 이력</h4>
      {reviews.data
        ?.filter((item) => item.related_case_id === pair.related.case.id)
        .map((review) => (
          <article className="panel" key={review.id}>
            <h4>비교 검토 {review.revision}</h4>
            <p>
              {review.recorded_by} · {date(review.created_at)}
            </p>
            <p>
              {review.stale
                ? "사건·학교 기준·검토 기록이 바뀐 과거 검토입니다."
                : "현재 사건과 일치하는 비교 검토입니다."}
            </p>
            <p>{review.reason}</p>
            <ul>
              {review.findings.map((finding, index) => (
                <li key={index}>
                  {categories[finding.category]} ·{" "}
                  {assessments[finding.assessment]}: {finding.detail}
                </li>
              ))}
            </ul>
          </article>
        ))}
    </section>
  );
}
