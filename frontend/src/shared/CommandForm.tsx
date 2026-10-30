import { useRef, useState, type ReactNode } from "react";
import {
  useIsMutating,
  useIsFetching,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useScope, useSession } from "../app/providers";
import { ApiError, command, type Command } from "../lib/api/client";
import { ErrorNotice } from "./ui";
import { useUnsavedChanges } from "./useUnsavedChanges";

export function CommandForm({
  caseId,
  version,
  path,
  method = "POST",
  button,
  children,
  versionField = "expected_version",
  transformValues,
  onSaved,
}: {
  caseId: string;
  version: number;
  path: string;
  method?: Command["method"];
  button: string;
  children?: ReactNode;
  versionField?: "expected_version" | "expected_settings_version";
  transformValues?: (
    values: Record<string, unknown>,
  ) => Record<string, unknown>;
  onSaved?: () => void;
}) {
  const { api } = useSession();
  const scope = useScope();
  const queries = useQueryClient();
  const form = useRef<HTMLFormElement>(null);
  const [saved, setSaved] = useState(false);
  const { dirty, setDirty } = useUnsavedChanges();
  const [failed, setFailed] = useState<Command | null>(null);
  const mutating = useIsMutating({
    mutationKey: ["case-command", ...scope, caseId],
  });
  const fetching = useIsFetching({
    queryKey:
      versionField === "expected_settings_version"
        ? ["school-settings", ...scope]
        : ["case", ...scope, caseId],
  });
  const busy = mutating > 0 || fetching > 0;
  const refresh = () =>
    Promise.all([
      queries.invalidateQueries({ queryKey: ["case", ...scope, caseId] }),
      queries.invalidateQueries({ queryKey: ["timeline", ...scope, caseId] }),
      queries.invalidateQueries({ queryKey: ["cases", ...scope] }),
      queries.invalidateQueries({ queryKey: ["my-tasks", ...scope] }),
      queries.invalidateQueries({ queryKey: ["runs", ...scope, caseId] }),
      queries.invalidateQueries({
        queryKey: ["support-decisions", ...scope, caseId],
      }),
      queries.invalidateQueries({
        queryKey: ["guardian-links", ...scope, caseId],
      }),
      queries.invalidateQueries({ queryKey: ["school-settings", ...scope] }),
      queries.invalidateQueries({ queryKey: ["school-members", ...scope] }),
      queries.invalidateQueries({ queryKey: ["school-contacts", ...scope] }),
      queries.invalidateQueries({ queryKey: ["notifications", ...scope] }),
      queries.invalidateQueries({
        queryKey: ["notification-status", ...scope],
      }),
    ]);
  const mutation = useMutation({
    mutationKey: ["case-command", ...scope, caseId],
    mutationFn: (cmd: Command) => api.execute<Record<string, unknown>>(cmd),
    onSuccess: async () => {
      setFailed(null);
      setSaved(true);
      setDirty(false);
      form.current?.reset();
      onSaved?.();
      await refresh();
    },
    onError: (error, cmd) => {
      setFailed(cmd);
      if (error instanceof ApiError && error.status === 409) void refresh();
    },
  });
  const uncertain =
    mutation.error instanceof ApiError && mutation.error.uncertain;
  return (
    <form
      ref={form}
      className="command-form"
      data-dirty={dirty ? "true" : undefined}
      onChange={() => setDirty(true)}
      onSubmit={(event) => {
        event.preventDefault();
        if (busy || failed) return;
        const values = Object.fromEntries(
          [...new FormData(event.currentTarget)].map(([key, value]) => [
            key,
            typeof value === "string" && !value.trim() ? null : value,
          ]),
        );
        setSaved(false);
        mutation.mutate(
          command(
            path,
            {
              ...(transformValues ? transformValues(values) : values),
              [versionField]: version,
            },
            method,
          ),
        );
      }}
    >
      <fieldset disabled={busy || !!failed}>
        {children}
        <button type="submit" className="primary">
          {busy ? "저장 중…" : button}
        </button>
      </fieldset>
      {saved ? (
        <p className="success" role="status">
          저장했습니다.
        </p>
      ) : null}
      {mutation.error ? (
        <ErrorNotice error={mutation.error}>
          {uncertain ? (
            <>
              <p>
                요청이 저장되었을 수 있습니다. 입력을 바꾸지 않고 같은 요청의
                처리 결과를 확인합니다.
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={() => failed && mutation.mutate(failed)}
              >
                같은 요청 다시 확인
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                await refresh();
                setFailed(null);
                mutation.reset();
              }}
            >
              최신 내용 확인 후 입력 계속
            </button>
          )}
        </ErrorNotice>
      ) : null}
    </form>
  );
}
