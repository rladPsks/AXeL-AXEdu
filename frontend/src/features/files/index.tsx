import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import { ApiError } from "../../lib/api/client";
import { date, Empty, ErrorNotice } from "../../shared/ui";
import { useUnsavedChanges } from "../../shared/useUnsavedChanges";

type PrivateFile = {
  id: string;
  filename: string;
  category: string;
  visibility: string;
  size_bytes: number;
  uploader_id: string;
  created_at: string;
};
type Upload = { path: string; key: string; file: File };

export function Files({
  caseId,
  version,
  closed,
}: {
  caseId: string;
  version: number;
  closed: boolean;
}) {
  const { api } = useSession();
  const scope = useScope();
  const queries = useQueryClient();
  const form = useRef<HTMLFormElement>(null);
  const { dirty, setDirty } = useUnsavedChanges();
  const [failed, setFailed] = useState<Upload | null>(null);
  const [saved, setSaved] = useState(false);
  const list = useQuery({
    queryKey: ["files", ...scope, caseId],
    queryFn: ({ signal }) =>
      api.get<PrivateFile[]>(
        `/api/cases/${encodeURIComponent(caseId)}/files`,
        signal,
      ),
  });
  const policy = useQuery({
    queryKey: ["file-policy", ...scope],
    queryFn: ({ signal }) =>
      api.get<{ max_bytes: number; extensions: string[] }>(
        "/api/file-policy",
        signal,
      ),
  });
  const refresh = () =>
    Promise.all([
      queries.invalidateQueries({ queryKey: ["files", ...scope, caseId] }),
      queries.invalidateQueries({ queryKey: ["case", ...scope, caseId] }),
      queries.invalidateQueries({ queryKey: ["timeline", ...scope, caseId] }),
    ]);
  const upload = useMutation({
    mutationFn: (input: Upload) =>
      api.upload(input.path, input.file, input.key),
    onSuccess: async () => {
      setFailed(null);
      setSaved(true);
      setDirty(false);
      form.current?.reset();
      await refresh();
    },
    onError: (error, input) => {
      setFailed(input);
      if (error instanceof ApiError && error.status === 409) void refresh();
    },
  });
  const download = useMutation({
    mutationFn: async (file: PrivateFile) => {
      const blob = await api.download(
        `/api/files/${encodeURIComponent(file.id)}/download`,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.filename;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
  });
  return (
    <>
      <h2>사건 자료</h2>
      <p className="hint">
        권한이 확인된 자료만 열람할 수 있습니다. 음성 업로드와 녹취 분석 동의는
        별도로 관리합니다.
      </p>
      {list.isPending ? (
        <p>자료를 불러오는 중…</p>
      ) : list.error ? (
        <ErrorNotice error={list.error} />
      ) : list.data.length === 0 ? (
        <Empty>등록한 자료가 없습니다.</Empty>
      ) : (
        list.data.map((file) => (
          <article className="work-item" key={file.id}>
            <div className="item-top">
              <strong>{file.filename}</strong>
              <button
                disabled={download.isPending}
                onClick={() => download.mutate(file)}
              >
                다운로드
              </button>
            </div>
            <p className="meta">
              {Math.ceil(file.size_bytes / 1024)} KB · 등록 {file.uploader_id} ·{" "}
              {file.visibility === "RESTRICTED"
                ? "등록자·관리자만 열람"
                : "사건 참여자 열람"}{" "}
              · {date(file.created_at)}
            </p>
          </article>
        ))
      )}
      {download.error ? <ErrorNotice error={download.error} /> : null}
      {!closed ? (
        <details className="new-request" open>
          <summary>자료 등록</summary>
          <form
            ref={form}
            data-dirty={dirty ? "true" : undefined}
            onChange={() => {
              setDirty(true);
              setSaved(false);
            }}
            onSubmit={(event) => {
              event.preventDefault();
              if (failed || upload.isPending) return;
              const data = new FormData(event.currentTarget);
              const file = data.get("file");
              if (!(file instanceof File) || !file.size) return;
              const params = new URLSearchParams({
                filename: file.name,
                expected_version: String(version),
                category: String(data.get("category")),
                visibility: String(data.get("visibility")),
              });
              setSaved(false);
              upload.mutate({
                path: `/api/cases/${encodeURIComponent(caseId)}/files?${params}`,
                key: crypto.randomUUID(),
                file,
              });
            }}
          >
            <fieldset
              disabled={upload.isPending || !!failed}
              style={{ border: 0, padding: 0, minWidth: 0 }}
            >
              <label>
                파일
                <input
                  name="file"
                  type="file"
                  required
                  accept={policy.data?.extensions.join(",")}
                />
              </label>
              {policy.data ? (
                <p className="hint">
                  파일당 최대 {Math.floor(policy.data.max_bytes / 1024 / 1024)}{" "}
                  MB. {policy.data.extensions.join(", ")}
                </p>
              ) : null}
              <label>
                자료 종류
                <select name="category">
                  <option value="EVIDENCE">사건 증거·메모</option>
                  <option value="SOURCE">근거 자료</option>
                  <option value="AUDIO">음성</option>
                  <option value="EXPORT">내보내기 자료</option>
                </select>
              </label>
              <label>
                열람 범위
                <select name="visibility">
                  <option value="CASE">사건 참여자</option>
                  <option value="RESTRICTED">등록자·관리자만</option>
                </select>
              </label>
              <button className="primary">
                {upload.isPending ? "업로드 중…" : "자료 저장"}
              </button>
            </fieldset>
          </form>
          {policy.error ? <ErrorNotice error={policy.error} /> : null}
          {saved ? (
            <p className="success" role="status">
              자료를 저장했습니다.
            </p>
          ) : null}
          {upload.error ? (
            <ErrorNotice error={upload.error}>
              {upload.error instanceof ApiError && upload.error.uncertain ? (
                <button
                  disabled={upload.isPending}
                  onClick={() => failed && upload.mutate(failed)}
                >
                  같은 파일 요청 다시 확인
                </button>
              ) : (
                <button
                  onClick={async () => {
                    await refresh();
                    setFailed(null);
                    upload.reset();
                  }}
                >
                  최신 내용 확인 후 다시 선택
                </button>
              )}
            </ErrorNotice>
          ) : null}
        </details>
      ) : null}
    </>
  );
}
