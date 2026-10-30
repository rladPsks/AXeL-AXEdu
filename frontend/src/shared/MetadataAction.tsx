import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useScope, useSession } from "../app/providers";
import { ApiError, command, type Command } from "../lib/api/client";
import { ErrorNotice } from "./ui";

export function MetadataAction({
  path,
  children,
}: {
  path: string;
  children: string;
}) {
  const { api } = useSession();
  const scope = useScope();
  const queries = useQueryClient();
  const [failed, setFailed] = useState<Command | null>(null);
  const mutation = useMutation({
    mutationFn: (cmd: Command) => api.execute(cmd),
    onSuccess: async () => {
      setFailed(null);
      await Promise.all([
        queries.invalidateQueries({ queryKey: ["notifications", ...scope] }),
        queries.invalidateQueries({
          queryKey: ["notification-status", ...scope],
        }),
      ]);
    },
    onError: (_error, cmd) => setFailed(cmd),
  });
  return (
    <>
      <button
        disabled={mutation.isPending || !!failed}
        onClick={() => mutation.mutate(command(path, {}))}
      >
        {mutation.isPending ? "처리 중…" : children}
      </button>
      {mutation.error ? (
        <ErrorNotice error={mutation.error}>
          {mutation.error instanceof ApiError && mutation.error.uncertain ? (
            <button
              disabled={mutation.isPending}
              onClick={() => failed && mutation.mutate(failed)}
            >
              같은 요청 다시 확인
            </button>
          ) : (
            <button
              onClick={() => {
                setFailed(null);
                mutation.reset();
              }}
            >
              오류 확인
            </button>
          )}
        </ErrorNotice>
      ) : null}
    </>
  );
}
