import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import { command } from "../../lib/api/client";
import type { CaseDetail } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { Badge, date, Empty, ErrorNotice } from "../../shared/ui";

type PrivateFile = { id: string; filename: string; category: string };
type Consent = {
  id: string;
  file_id: string;
  subject: string;
  scope: string;
  confirmed_by: string;
  confirmed_at: string;
  revoked_at: string | null;
  revoke_reason: string | null;
};
type Segment = {
  id: string;
  start: number;
  end: number;
  speaker: string;
  text: string;
};
type Transcript = {
  id: string;
  revision: number;
  reason: string | null;
  created_by: string;
  created_at: string;
  segments: Segment[];
};
type SummaryItem = { text: string; segment_ids: string[] };
type Run = {
  run_id: string;
  purpose: string;
  status: string;
  error: { message: string } | null;
  result:
    | (Record<string, unknown> & {
        segments?: Segment[];
        requests?: SummaryItem[];
        claims?: SummaryItem[];
        commitments?: SummaryItem[];
        needs_check?: SummaryItem[];
        unclear_segment_ids?: string[];
      })
    | null;
  input_refs: { resource_type: string; resource_id: string; version: number }[];
  created_at: string;
};

const clock = (s: number) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export function Recordings({ record }: { record: CaseDetail }) {
  const { api } = useSession();
  const scope = useScope();
  const files = useQuery({
    queryKey: ["files", ...scope, record.id],
    queryFn: ({ signal }) =>
      api.get<PrivateFile[]>(
        `/api/cases/${encodeURIComponent(record.id)}/files`,
        signal,
      ),
  });
  const consents = useQuery({
    queryKey: ["consents", ...scope, record.id],
    queryFn: ({ signal }) =>
      api.get<Consent[]>(
        `/api/cases/${encodeURIComponent(record.id)}/audio-consents`,
        signal,
      ),
  });
  const caps = useQuery({
    queryKey: ["agent-capabilities", ...scope],
    queryFn: ({ signal }) =>
      api.get<{ purpose: string }[]>("/api/agent-capabilities", signal),
  });
  const runs = useQuery({
    queryKey: ["runs", ...scope, record.id],
    queryFn: ({ signal }) =>
      api.get<Run[]>(
        `/api/cases/${encodeURIComponent(record.id)}/agent-runs`,
        signal,
      ),
    refetchInterval: (q) =>
      q.state.data?.some(
        (r) =>
          ["TRANSCRIBE_AUDIO", "SUMMARIZE_TRANSCRIPT"].includes(r.purpose) &&
          ["QUEUED", "RUNNING"].includes(r.status),
      )
        ? 1500
        : false,
  });
  const audio = (files.data ?? []).filter((f) => f.category === "AUDIO");
  const has = (p: string) => !!caps.data?.some((c) => c.purpose === p);
  return (
    <>
      <h2>동의 녹취·전사</h2>
      <p className="hint">
        음성은 녹취 대상자의 동의를 확인해 기록한 뒤에만 전사합니다. 전사 결과는
        “기록된 발화”이며 확인된 사실이 아닙니다. 화자 구분은 자동 번호이고
        사람의 역할이나 신원을 뜻하지 않습니다. 반드시 음성을 들으며 대조하고
        정정하세요.
      </p>
      {!caps.isPending && !has("TRANSCRIBE_AUDIO") ? (
        <div className="notice">
          음성 전사(Azure AI Speech) 연결 설정이 준비되지 않았습니다. 동의
          기록과 수동 확인은 계속 사용할 수 있습니다.
        </div>
      ) : null}
      {files.error ? <ErrorNotice error={files.error} /> : null}
      {consents.error ? <ErrorNotice error={consents.error} /> : null}
      {files.isPending ? (
        <p>음성 자료를 불러오는 중…</p>
      ) : audio.length === 0 ? (
        <Empty>
          “민원 자료” 탭에서 자료 종류를 “음성”으로 등록하면 여기에 표시됩니다.
        </Empty>
      ) : (
        audio.map((file) => (
          <AudioCard
            key={file.id}
            file={file}
            record={record}
            consents={(consents.data ?? []).filter(
              (c) => c.file_id === file.id,
            )}
            runs={(runs.data ?? []).filter((r) =>
              r.input_refs.some(
                (ref) =>
                  ref.resource_type === "FILE" && ref.resource_id === file.id,
              ),
            )}
            allRuns={runs.data ?? []}
            canTranscribe={has("TRANSCRIBE_AUDIO")}
            canSummarize={has("SUMMARIZE_TRANSCRIPT")}
          />
        ))
      )}
    </>
  );
}

function AudioCard({
  file,
  record,
  consents,
  runs,
  allRuns,
  canTranscribe,
  canSummarize,
}: {
  file: PrivateFile;
  record: CaseDetail;
  consents: Consent[];
  runs: Run[];
  allRuns: Run[];
  canTranscribe: boolean;
  canSummarize: boolean;
}) {
  const { api } = useSession();
  const scope = useScope();
  const queries = useQueryClient();
  const player = useRef<HTMLAudioElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const active = consents.find((c) => !c.revoked_at);
  const open = record.status === "OPEN";
  const transcripts = useQuery({
    queryKey: ["transcripts", ...scope, record.id, file.id],
    enabled: !!active,
    queryFn: ({ signal }) =>
      api.get<Transcript[]>(
        `/api/cases/${encodeURIComponent(record.id)}/transcripts?file_id=${encodeURIComponent(file.id)}`,
        signal,
      ),
  });
  const refresh = () => {
    void queries.invalidateQueries({ queryKey: ["consents", ...scope] });
    void queries.invalidateQueries({ queryKey: ["transcripts", ...scope] });
    void queries.invalidateQueries({ queryKey: ["runs", ...scope] });
  };
  const load = useMutation({
    mutationFn: async () => {
      const blob = await api.download(
        `/api/files/${encodeURIComponent(file.id)}/download`,
      );
      setSrc((old) => {
        if (old) URL.revokeObjectURL(old);
        return URL.createObjectURL(blob);
      });
    },
  });
  const start = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.execute(
        command(`/api/cases/${encodeURIComponent(record.id)}/agent-runs`, {
          expected_version: record.version,
          ...body,
        }),
      ),
    onSuccess: refresh,
  });
  const versions = transcripts.data ?? [];
  const latest = versions[versions.length - 1];
  const transcribeRuns = runs.filter((r) => r.purpose === "TRANSCRIBE_AUDIO");
  const usable = transcribeRuns.find(
    (r) => r.status === "SUCCEEDED" && r.result?.segments,
  );
  const summaryRuns = allRuns.filter(
    (r) =>
      r.purpose === "SUMMARIZE_TRANSCRIPT" &&
      r.input_refs.some(
        (ref) =>
          ref.resource_type === "TRANSCRIPT" &&
          versions.some((t) => t.id === ref.resource_id),
      ),
  );
  const seek = (s: number) => {
    if (player.current) {
      player.current.currentTime = s;
      void player.current.play().catch(() => undefined);
    }
  };
  return (
    <article className="work-item">
      <div className="item-top">
        <strong>{file.filename}</strong>
        <button disabled={load.isPending} onClick={() => load.mutate()}>
          {src ? "다시 불러오기" : "음성 불러오기"}
        </button>
      </div>
      {src ? <audio ref={player} src={src} controls /> : null}
      {load.error ? <ErrorNotice error={load.error} /> : null}

      {!active ? (
        <>
          {consents.some((c) => c.revoked_at) ? (
            <div className="notice">
              동의가 철회되어 전사·요약에 사용할 수 없습니다. 다시 동의를 받은
              뒤 기록하세요.
            </div>
          ) : null}
          <h3>녹취 동의 확인</h3>
          {open ? (
            <CommandForm
              caseId={record.id}
              version={record.version}
              path={`/api/cases/${encodeURIComponent(record.id)}/audio-consents`}
              button="동의 확인 기록"
              onSaved={refresh}
            >
              <input type="hidden" name="file_id" value={file.id} />
              <label>
                동의한 사람과 관계
                <input name="subject" required maxLength={10000} />
              </label>
              <label>
                동의 범위와 확인 방법
                <textarea name="scope" required maxLength={10000} />
              </label>
            </CommandForm>
          ) : (
            <Empty>종결된 민원에서는 새 동의를 기록할 수 없습니다.</Empty>
          )}
        </>
      ) : (
        <>
          <p className="meta">
            동의 확인 {active.subject} · {active.confirmed_by} ·{" "}
            {date(active.confirmed_at)}
          </p>
          <details className="new-request">
            <summary>동의 철회</summary>
            <p className="hint">
              철회하면 이후 전사·요약 요청이 중단됩니다. 이미 저장된 전사본의
              보관·삭제는 학교 정책에 따릅니다.
            </p>
            <CommandForm
              caseId={record.id}
              version={record.version}
              path={`/api/audio-consents/${encodeURIComponent(active.id)}/revoke`}
              button="동의 철회"
              onSaved={refresh}
            >
              <label>
                철회 사유
                <textarea name="reason" required maxLength={10000} />
              </label>
            </CommandForm>
          </details>

          {!latest ? (
            <>
              <h3>전사</h3>
              <button
                className="primary"
                disabled={!canTranscribe || !open || start.isPending}
                onClick={() =>
                  start.mutate({
                    purpose: "TRANSCRIBE_AUDIO",
                    input_refs: [
                      {
                        resource_type: "FILE",
                        resource_id: file.id,
                        version: 1,
                      },
                    ],
                  })
                }
              >
                {start.isPending ? "요청 중…" : "전사 시작"}
              </button>
              {start.error ? <ErrorNotice error={start.error} /> : null}
              {transcribeRuns.map((run) => (
                <div className="work-item" key={run.run_id}>
                  <div className="item-top">
                    <strong>전사 실행</strong>
                    <Badge value={run.status} />
                  </div>
                  {["QUEUED", "RUNNING"].includes(run.status) ? (
                    <p role="status">음성을 전사하고 있습니다…</p>
                  ) : null}
                  {run.error ? (
                    <div className="notice error" role="alert">
                      {run.error.message}
                    </div>
                  ) : null}
                  {run.status === "WAITING_REVIEW" && run.result?.segments ? (
                    <>
                      <SegmentTable
                        segments={run.result.segments}
                        seek={seek}
                      />
                      <CommandForm
                        caseId={record.id}
                        version={record.version}
                        path={`/api/agent-runs/${encodeURIComponent(run.run_id)}/review`}
                        button="음성과 대조했음을 확인"
                        onSaved={refresh}
                      >
                        <input type="hidden" name="decision" value="ACCEPT" />
                        <label>
                          대조 내용
                          <textarea name="reason" required maxLength={10000} />
                        </label>
                      </CommandForm>
                    </>
                  ) : null}
                </div>
              ))}
              {usable ? (
                <CommandForm
                  caseId={record.id}
                  version={record.version}
                  path={`/api/cases/${encodeURIComponent(record.id)}/transcripts`}
                  button="확인한 전사를 원본 버전으로 저장"
                  onSaved={refresh}
                >
                  <input type="hidden" name="file_id" value={file.id} />
                  <input type="hidden" name="run_id" value={usable.run_id} />
                </CommandForm>
              ) : null}
            </>
          ) : (
            <>
              <h3>
                전사본 버전 {latest.revision}
                {versions.length > 1
                  ? ` (이전 ${versions.length - 1}개 보존)`
                  : ""}
              </h3>
              <p className="meta">
                {latest.created_by} · {date(latest.created_at)}
                {latest.reason ? ` · 정정 사유: ${latest.reason}` : " · 원본"}
              </p>
              <SegmentTable segments={latest.segments} seek={seek} />
              {open ? (
                <details className="new-request">
                  <summary>전사 정정 (새 버전으로 저장)</summary>
                  <CommandForm
                    key={latest.id}
                    caseId={record.id}
                    version={record.version}
                    path={`/api/cases/${encodeURIComponent(record.id)}/transcripts`}
                    button="정정본 저장"
                    onSaved={refresh}
                    transformValues={(v) => ({
                      file_id: file.id,
                      reason: v.reason,
                      edits: latest.segments.map((s) => ({
                        id: s.id,
                        text: v[`text:${s.id}`],
                        speaker: v[`speaker:${s.id}`],
                      })),
                    })}
                  >
                    {latest.segments.map((s) => (
                      <div key={s.id}>
                        <label>
                          {clock(s.start)} 화자
                          <input
                            name={`speaker:${s.id}`}
                            defaultValue={s.speaker}
                            required
                            maxLength={100}
                          />
                        </label>
                        <label>
                          내용
                          <textarea
                            name={`text:${s.id}`}
                            defaultValue={s.text}
                            required
                            maxLength={10000}
                          />
                        </label>
                      </div>
                    ))}
                    <label>
                      정정 사유
                      <textarea name="reason" required maxLength={10000} />
                    </label>
                  </CommandForm>
                </details>
              ) : null}
              {versions.length > 1 ? (
                <details>
                  <summary>이전 버전 보기</summary>
                  {versions
                    .slice(0, -1)
                    .reverse()
                    .map((t) => (
                      <div key={t.id}>
                        <p className="meta">
                          버전 {t.revision} · {date(t.created_at)}
                        </p>
                        <SegmentTable segments={t.segments} seek={seek} />
                      </div>
                    ))}
                </details>
              ) : null}

              <h3>발화 요약 — 확인된 사실 아님</h3>
              <button
                disabled={!canSummarize || !open || start.isPending}
                onClick={() =>
                  start.mutate({
                    purpose: "SUMMARIZE_TRANSCRIPT",
                    input_refs: [
                      {
                        resource_type: "TRANSCRIPT",
                        resource_id: latest.id,
                        version: latest.revision,
                      },
                    ],
                  })
                }
              >
                요약 생성
              </button>
              {!canSummarize ? (
                <p className="hint">
                  OpenAI 연결이 없어 요약을 만들 수 없습니다.
                </p>
              ) : null}
              {start.error ? <ErrorNotice error={start.error} /> : null}
              {summaryRuns.map((run) => (
                <Summary
                  key={run.run_id}
                  run={run}
                  record={record}
                  seek={seek}
                  segments={latest.segments}
                  onSaved={refresh}
                />
              ))}
            </>
          )}
        </>
      )}
    </article>
  );
}

function SegmentTable({
  segments,
  seek,
}: {
  segments: Segment[];
  seek: (s: number) => void;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>시간</th>
          <th>화자(자동 번호)</th>
          <th>기록된 발화</th>
        </tr>
      </thead>
      <tbody>
        {segments.map((s) => (
          <tr key={s.id} id={`segment-${s.id}`}>
            <td>
              <button type="button" onClick={() => seek(s.start)}>
                {clock(s.start)}
              </button>
            </td>
            <td>{s.speaker}</td>
            <td className="preserve">{s.text}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Summary({
  run,
  record,
  seek,
  segments,
  onSaved,
}: {
  run: Run;
  record: CaseDetail;
  seek: (s: number) => void;
  segments: Segment[];
  onSaved: () => void;
}) {
  const start = (id: string) => segments.find((s) => s.id === id)?.start ?? 0;
  const groups: [string, keyof NonNullable<Run["result"]>][] = [
    ["요청으로 기록된 발화", "requests"],
    ["주장으로 기록된 발화", "claims"],
    ["약속·조치로 기록된 발화", "commitments"],
    ["추가 확인이 필요한 부분", "needs_check"],
  ];
  return (
    <div className="work-item">
      <div className="item-top">
        <strong>발화 요약</strong>
        <Badge value={run.status} />
      </div>
      {["QUEUED", "RUNNING"].includes(run.status) ? (
        <p role="status">요약을 만들고 있습니다…</p>
      ) : null}
      {run.error ? (
        <div className="notice error" role="alert">
          {run.error.message}
        </div>
      ) : null}
      {run.result ? (
        <>
          <p className="hint">
            아래는 녹취에 기록된 발화의 정리이며 사실로 확인된 내용이 아닙니다.
            근거 구간을 눌러 음성과 대조하세요.
          </p>
          {groups.map(([title, key]) => {
            const items =
              (run.result?.[key] as SummaryItem[] | undefined) ?? [];
            return items.length ? (
              <div key={key}>
                <h4>{title}</h4>
                <ul>
                  {items.map((item, i) => (
                    <li key={i}>
                      {item.text}{" "}
                      {item.segment_ids.map((id) => (
                        <a
                          key={id}
                          href={`#segment-${id}`}
                          onClick={() => seek(start(id))}
                        >
                          [{id}]{" "}
                        </a>
                      ))}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null;
          })}
          {run.result.unclear_segment_ids?.length ? (
            <p>
              잘 들리지 않거나 불분명한 구간:{" "}
              {run.result.unclear_segment_ids.join(", ")}
            </p>
          ) : null}
        </>
      ) : null}
      {run.status === "WAITING_REVIEW" ? (
        <CommandForm
          caseId={record.id}
          version={record.version}
          path={`/api/agent-runs/${encodeURIComponent(run.run_id)}/review`}
          button="원문 대조 후 검토 완료"
          onSaved={onSaved}
        >
          <input type="hidden" name="decision" value="ACCEPT" />
          <label>
            검토 내용
            <textarea name="reason" required maxLength={10000} />
          </label>
        </CommandForm>
      ) : null}
    </div>
  );
}
