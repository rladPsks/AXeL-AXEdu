import { useState } from "react";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import type { CaseDetail } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { date, ErrorNotice, label } from "../../shared/ui";
import { koreanTime, localInput } from "../../shared/dates";
import { ComparisonReviewPanel } from "./ReviewPanel";

export type DocumentVersion = {
  id: string;
  document_id: string;
  case_id: string;
  kind: string;
  label: string;
  revision: number;
  content: string;
  provenance: string;
  occurred_at: string;
  delivery_state: string;
  recorded_by: string;
  file_id: string | null;
};
type Relation = {
  id: string;
  left_case_id: string;
  right_case_id: string;
  revision: number;
  state: string;
  basis: string;
  reason: string;
  recorded_by: string;
};
type Candidate = {
  id: string;
  title: string;
  status: string;
  version: number;
  received_at: string;
  matches: string[];
};
type Comparison = {
  profile: {
    person_key: string | null;
    issue_key: string | null;
    received_at: string;
  } | null;
  policy: {
    configured: boolean;
    window_days: number | null;
    minimum_count: number | null;
    response_delay_hours: number | null;
  };
  candidates: Candidate[];
  candidate_count: number;
  count_including_current: number;
  review_threshold_met: boolean | null;
  relations: Relation[];
  next_cursor: string | null;
};
const kinds: Record<string, string> = {
  INTAKE: "접수 원문",
  EVIDENCE: "추가 증거",
  OFFICIAL_DOCUMENT: "공문·근거",
  RESPONSE: "이전 답변",
  ACTION: "조치 기록",
};
const states: Record<string, string> = {
  DELIVERED: "전달됨으로 기록",
  NOT_DELIVERED: "미전달로 기록",
  UNKNOWN: "전달 여부 미확인",
  NOT_APPLICABLE: "전달 여부 해당 없음",
};
const bases: Record<string, string> = {
  SAME_PERSON: "동일인 코드",
  SAME_ISSUE: "동일 사안 코드",
  BOTH: "동일인·동일 사안",
};

type Attachment = { id: string; filename: string; category: string };
function VersionFields({ files }: { files: Attachment[] }) {
  return (
    <>
      <label>
        원문·정정 내용
        <textarea name="content" required maxLength={10000} />
      </label>
      <label>
        출처·확인 경위
        <textarea name="provenance" required maxLength={10000} />
      </label>
      <label>
        기록 대상 시각 (한국 시간)
        <input type="datetime-local" name="occurred_at" required />
      </label>
      <label>
        답변 전달 기록
        <select name="delivery_state">
          <option value="UNKNOWN">전달 여부 미확인</option>
          <option value="NOT_APPLICABLE">전달 여부 해당 없음</option>
          <option value="DELIVERED">전달됨으로 기록 (답변만)</option>
          <option value="NOT_DELIVERED">미전달로 기록 (답변만)</option>
        </select>
      </label>
      <label>
        함께 보존할 사건 자료 (선택)
        <select name="file_id">
          <option value="">자료 파일 없음</option>
          {files
            .filter((file) => file.category !== "AUDIO")
            .map((file) => (
              <option key={file.id} value={file.id}>
                {file.filename}
              </option>
            ))}
        </select>
      </label>
    </>
  );
}
const versionValues = (values: Record<string, unknown>) => ({
  ...values,
  occurred_at: koreanTime(values.occurred_at),
});

export function CaseDocuments({ record }: { record: CaseDetail }) {
  const { api } = useSession();
  const scope = useScope();
  const files = useQuery({
    queryKey: ["files", ...scope, record.id],
    queryFn: ({ signal }) =>
      api.get<Attachment[]>(
        `/api/cases/${encodeURIComponent(record.id)}/files`,
        signal,
      ),
  });
  const query = useQuery<DocumentVersion[]>({
    queryKey: ["documents", ...scope, record.id, record.version],
    placeholderData: (previous) => previous,
    queryFn: ({ signal }) =>
      api.get<DocumentVersion[]>(
        `/api/cases/${encodeURIComponent(record.id)}/documents`,
        signal,
      ),
  });
  const latest = new Map<string, DocumentVersion>();
  for (const item of query.data ?? [])
    if (
      !latest.has(item.document_id) ||
      latest.get(item.document_id)!.revision < item.revision
    )
      latest.set(item.document_id, item);
  return (
    <>
      <h2>원문·답변 기록</h2>
      {files.error ? <ErrorNotice error={files.error} /> : null}
      <p>
        접수 원문·새 증거·이전 답변·조치를 버전별로 보존합니다. 이 화면의 전달
        여부는 사람이 입력한 기록이며 실제 전송을 수행하지 않습니다.
      </p>
      {query.error ? <ErrorNotice error={query.error} /> : null}
      {record.status !== "CLOSED" ? (
        <details>
          <summary>새 원문·증거 기록</summary>
          <CommandForm
            caseId={record.id}
            version={record.version}
            path={`/api/cases/${encodeURIComponent(record.id)}/documents`}
            button="원문 기록 저장"
            disabled={query.isFetching}
            transformValues={versionValues}
          >
            <label>
              자료 구분
              <select name="kind">
                {Object.entries(kinds).map(([key, value]) => (
                  <option key={key} value={key}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              자료 제목
              <input name="label" required maxLength={128} />
            </label>
            <VersionFields files={files.data ?? []} />
          </CommandForm>
        </details>
      ) : (
        <p>새 자료는 사건 재개 후 기록하세요.</p>
      )}
      {query.data?.length === 0 ? (
        <p>아직 저장된 원문 버전이 없습니다.</p>
      ) : null}
      {[...latest.values()].map((document) => (
        <article className="panel" key={document.document_id}>
          <h3>
            {document.label} · {kinds[document.kind]}
          </h3>
          <p className="meta">
            최신 버전 {document.revision} · {date(document.occurred_at)} ·{" "}
            {document.recorded_by}
          </p>
          <p style={{ whiteSpace: "pre-wrap" }}>{document.content}</p>
          <p>출처·경위: {document.provenance}</p>
          <p>{states[document.delivery_state]}</p>
          <details>
            <summary>모든 버전 대조</summary>
            {query.data
              ?.filter((item) => item.document_id === document.document_id)
              .map((item) => (
                <section key={item.id}>
                  <h4>
                    버전 {item.revision} · {date(item.occurred_at)}
                  </h4>
                  <p style={{ whiteSpace: "pre-wrap" }}>{item.content}</p>
                  <p>
                    {item.provenance} · {states[item.delivery_state]}
                  </p>
                </section>
              ))}
          </details>
          {record.status !== "CLOSED" ? (
            <details>
              <summary>정정 버전 추가</summary>
              <CommandForm
                caseId={record.id}
                version={record.version}
                path={`/api/documents/${encodeURIComponent(document.document_id)}/versions`}
                button="정정 버전 저장"
                disabled={query.isFetching}
                transformValues={(values) => ({
                  ...versionValues(values),
                  expected_document_revision: Number(
                    values.expected_document_revision,
                  ),
                })}
              >
                <input
                  type="hidden"
                  name="expected_document_revision"
                  value={document.revision}
                />
                <VersionFields files={files.data ?? []} />
              </CommandForm>
            </details>
          ) : null}
        </article>
      ))}
    </>
  );
}

export type PairEvidence = {
  case: { id: string; title: string; version: number; status: string };
  documents: DocumentVersion[];
  tasks: {
    id: string;
    question: string;
    status: string;
    reply: string | null;
  }[];
  support_requests: {
    id: string;
    reason: string;
    status: string;
    result: string | null;
  }[];
  response_review: {
    review_due_from_records: boolean | null;
    delivered_response_recorded: boolean;
    notice: string;
  };
};
function Evidence({ item }: { item: PairEvidence }) {
  return (
    <section className="panel">
      <h3>{item.case.title}</h3>
      <p>
        {item.case.id} · 사건 버전 {item.case.version}
      </p>
      <p className="notice">
        {item.response_review.review_due_from_records === true
          ? "학교 기준에 따라 답변 기록 재확인이 필요합니다."
          : item.response_review.delivered_response_recorded
            ? "전달됨으로 입력한 답변 기록이 있습니다."
            : "저장된 답변·학교 기준을 대조하세요."}{" "}
        {item.response_review.notice}
      </p>
      {item.documents.length === 0 ? (
        <p>저장된 원문 버전이 없습니다. 실제 자료가 없다는 뜻은 아닙니다.</p>
      ) : (
        item.documents.map((document) => (
          <details key={document.id}>
            <summary>
              {kinds[document.kind]} · {document.label} · 버전{" "}
              {document.revision} · {date(document.occurred_at)}
            </summary>
            <p style={{ whiteSpace: "pre-wrap" }}>{document.content}</p>
            <p>
              {states[document.delivery_state]} · {document.provenance}
            </p>
          </details>
        ))
      )}
      <h4>업무·미이행 확인</h4>
      <ul>
        {item.tasks.map((task) => (
          <li key={task.id}>
            {task.question} · {label(task.status)}
            <p>{task.reply ?? "회신 기록 없음"}</p>
          </li>
        ))}
      </ul>
      <h4>학교 지원 기록</h4>
      <ul>
        {item.support_requests.map((request) => (
          <li key={request.id}>
            {request.reason} · {label(request.status)}
            <p>{request.result ?? "결과 기록 없음"}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function CaseComparison({ record }: { record: CaseDetail }) {
  const { api } = useSession();
  const scope = useScope();
  const queries = useQueryClient();
  const [related, setRelated] = useState("");
  const chooseRelated = (next: string) => {
    if (
      next !== related &&
      document.querySelector('.comparison-review form[data-dirty="true"]') &&
      !window.confirm(
        "저장하지 않은 비교 검토가 있습니다. 다른 사건을 대조하면 입력이 사라집니다. 이동할까요?",
      )
    )
      return;
    setRelated(next);
  };
  const list = useInfiniteQuery({
    queryKey: ["comparison", ...scope, record.id, record.version],
    initialPageParam: "",
    queryFn: ({ pageParam, signal }) =>
      api.get<Comparison>(
        `/api/cases/${encodeURIComponent(record.id)}/comparison?after=${encodeURIComponent(pageParam)}`,
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const settings = useQuery({
    queryKey: ["repeat-settings", ...scope],
    queryFn: ({ signal }) =>
      api.get<{
        settings_version: number;
        window_days: number | null;
        minimum_count: number | null;
        response_delay_hours: number | null;
      }>("/api/school/repeat-settings", signal),
  });
  const pair = useQuery<{
    current: PairEvidence;
    related: PairEvidence;
    relation_history: Relation[];
    notice: string;
  }>({
    queryKey: ["comparison-pair", ...scope, record.id, record.version, related],
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey.at(-1) === related &&
      previousQuery?.queryKey.at(-3) === record.id
        ? previous
        : undefined,
    enabled: !!related,
    queryFn: ({ signal }) =>
      api.get<{
        current: PairEvidence;
        related: PairEvidence;
        relation_history: Relation[];
        notice: string;
      }>(
        `/api/cases/${encodeURIComponent(record.id)}/compare/${encodeURIComponent(related)}`,
        signal,
      ),
  });
  const first = list.data?.pages[0];
  const currentRelation = pair.data?.relation_history[0];
  return (
    <>
      <h2>반복·추가 사실 검토</h2>
      <button
        disabled={list.isFetching || settings.isFetching || pair.isFetching}
        onClick={() => {
          void list.refetch();
          void settings.refetch();
          void queries.invalidateQueries({
            queryKey: ["comparison-inputs", ...scope],
          });
          void queries.invalidateQueries({
            queryKey: ["comparison-reviews", ...scope],
          });
          if (related) void pair.refetch();
        }}
      >
        비교 자료 새로고침
      </button>
      <p>
        같은 코드가 있는 사건을 후보로 보여줍니다. 동일인·동일 사안 여부와
        미응답·새 증거는 원문을 대조한 사람이 판단합니다.
      </p>
      {list.error ? <ErrorNotice error={list.error} /> : null}
      {settings.error ? <ErrorNotice error={settings.error} /> : null}
      {first ? (
        <p className="notice">
          {first.policy.configured
            ? `학교 검토 기준: ${first.policy.window_days}일 · ${first.policy.minimum_count}건. 현재 사건 포함 후보 ${first.count_including_current}건${first.review_threshold_met ? " — 검토 기준에 도달했습니다" : ""}.`
            : "학교 반복 검토 기준이 아직 없습니다. 횟수 기준이나 법정 기한을 자동 적용하지 않습니다."}{" "}
          후보 수는 반복 민원 확정 횟수가 아닙니다.
        </p>
      ) : null}
      {record.status !== "CLOSED" ? (
        <details>
          <summary>동일인·동일 사안 비교 코드</summary>
          <p>
            학교 내부에서 정한 구분 코드를 사용하세요. 주민등록번호나 연락처를
            입력하지 마세요.
          </p>
          <CommandForm
            caseId={record.id}
            version={record.version}
            path={`/api/cases/${encodeURIComponent(record.id)}/comparison-profile`}
            method="PUT"
            button="비교 코드 저장"
            transformValues={(values) => ({
              ...values,
              received_at: koreanTime(values.received_at),
            })}
          >
            <label>
              동일인 구분 코드
              <input
                name="person_key"
                maxLength={128}
                defaultValue={first?.profile?.person_key ?? ""}
              />
            </label>
            <label>
              동일 사안 구분 코드
              <input
                name="issue_key"
                maxLength={128}
                defaultValue={first?.profile?.issue_key ?? ""}
              />
            </label>
            <label>
              접수 시각 (한국 시간)
              <input
                type="datetime-local"
                name="received_at"
                defaultValue={localInput(first?.profile?.received_at)}
                required
              />
            </label>
          </CommandForm>
        </details>
      ) : null}
      {settings.data ? (
        <details>
          <summary>학교의 반복·지연 검토 기준</summary>
          <p>법정 규정이 아닌 학교 운영상 재확인 기준입니다.</p>
          <CommandForm
            caseId={record.id}
            version={settings.data.settings_version}
            versionField="expected_settings_version"
            path="/api/school/repeat-settings"
            method="PUT"
            button="반복 검토 기준 저장"
            transformValues={(values) => ({
              ...values,
              window_days: Number(values.window_days),
              minimum_count: Number(values.minimum_count),
              response_delay_hours: values.response_delay_hours
                ? Number(values.response_delay_hours)
                : null,
            })}
          >
            <label>
              비교 기간 (일)
              <input
                type="number"
                name="window_days"
                min={1}
                max={3650}
                defaultValue={settings.data.window_days ?? ""}
                required
              />
            </label>
            <label>
              재확인 건수 (현재 사건 포함)
              <input
                type="number"
                name="minimum_count"
                min={2}
                max={1000}
                defaultValue={settings.data.minimum_count ?? ""}
                required
              />
            </label>
            <label>
              답변 기록 재확인 기준 (시간, 선택)
              <input
                type="number"
                name="response_delay_hours"
                min={1}
                max={8760}
                defaultValue={settings.data.response_delay_hours ?? ""}
              />
            </label>
          </CommandForm>
        </details>
      ) : null}
      <h3>비교 후보</h3>
      {first && !first.profile ? (
        <p>비교 코드를 먼저 기록하세요.</p>
      ) : first?.candidate_count === 0 ? (
        <p>현재 코드와 기간에서 일치하는 다른 사건이 없습니다.</p>
      ) : null}
      {list.data?.pages
        .flatMap((page) => page.candidates)
        .map((candidate) => (
          <div className="panel" key={candidate.id}>
            <h4>{candidate.title}</h4>
            <p>
              {candidate.id} ·{" "}
              {candidate.matches.map((match) => bases[match]).join(", ")} ·{" "}
              {date(candidate.received_at)}
            </p>
            <button onClick={() => chooseRelated(candidate.id)}>
              원문 대조: {candidate.id}
            </button>
          </div>
        ))}
      {list.hasNextPage ? (
        <button
          disabled={list.isFetching}
          onClick={() => void list.fetchNextPage()}
        >
          후보 더 보기
        </button>
      ) : null}
      <h3>연결·분리 이력의 현재 상태</h3>
      {first?.relations.map((relation) => {
        const other =
          relation.left_case_id === record.id
            ? relation.right_case_id
            : relation.left_case_id;
        return (
          <div key={relation.id}>
            <p>
              {other} ·{" "}
              {relation.state === "LINKED"
                ? "연결 검토됨"
                : "별도 사건으로 분리"}{" "}
              · {bases[relation.basis]}
            </p>
            <p>{relation.reason}</p>
            <button onClick={() => chooseRelated(other)}>
              연결 사건 대조: {other}
            </button>
          </div>
        );
      })}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          chooseRelated(
            String(
              new FormData(event.currentTarget).get("related") ?? "",
            ).trim(),
          );
        }}
      >
        <label>
          직접 비교할 사건 ID
          <input name="related" required maxLength={128} />
        </label>
        <button>사건 대조</button>
      </form>
      {pair.error ? <ErrorNotice error={pair.error} /> : null}
      {pair.data ? (
        <>
          <p className="notice">{pair.data.notice}</p>
          <div className="comparison-columns">
            <Evidence item={pair.data.current} />
            <Evidence item={pair.data.related} />
          </div>
          <ComparisonReviewPanel
            key={`${record.id}:${related}`}
            record={record}
            pair={pair.data}
            ready={
              !pair.isFetching &&
              pair.data.current.case.version === record.version
            }
          />
          {record.status !== "CLOSED" &&
          pair.data.related.case.status !== "CLOSED" ? (
            <CommandForm
              caseId={record.id}
              version={record.version}
              path={`/api/cases/${encodeURIComponent(record.id)}/relations`}
              button="연결·분리 판단 저장"
              disabled={pair.isFetching}
              onSaved={() => {
                void queries.invalidateQueries({
                  queryKey: ["case", ...scope],
                });
              }}
              transformValues={(values) => ({
                ...values,
                expected_related_version: Number(
                  values.expected_related_version,
                ),
              })}
            >
              <input type="hidden" name="related_case_id" value={related} />
              <input
                type="hidden"
                name="expected_related_version"
                value={pair.data.related.case.version}
              />
              <input
                type="hidden"
                name="previous_relation_id"
                value={currentRelation?.id ?? ""}
              />
              <label>
                검토 결과
                <select name="state">
                  <option value="LINKED">관련 사건으로 연결</option>
                  <option value="SEPARATED">별도 사건으로 분리</option>
                </select>
              </label>
              <label>
                대조 기준
                <select name="basis">
                  <option value="SAME_ISSUE">동일 사안</option>
                  <option value="SAME_PERSON">동일인</option>
                  <option value="BOTH">동일인·동일 사안</option>
                </select>
              </label>
              <label>
                연결·분리 사유
                <textarea name="reason" required maxLength={10000} />
              </label>
            </CommandForm>
          ) : (
            <p>연결·분리는 양쪽 사건을 재개한 후 변경할 수 있습니다.</p>
          )}
          <details>
            <summary>이전 연결·분리 판단</summary>
            {pair.data.relation_history.map((relation) => (
              <p key={relation.id}>
                판단 {relation.revision} ·{" "}
                {relation.state === "LINKED" ? "연결" : "분리"} ·{" "}
                {relation.reason} · {relation.recorded_by}
              </p>
            ))}
          </details>
        </>
      ) : related && pair.isFetching ? (
        <p role="status">비교 자료를 불러오는 중…</p>
      ) : null}
    </>
  );
}
