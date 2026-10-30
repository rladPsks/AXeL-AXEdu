export type DemoAccount = {
  id: string;
  name: string;
  role: "ADMIN" | "TEACHER" | "GUARDIAN";
  kind: "STAFF" | "GUARDIAN";
};
export type GuardianSession = {
  guardian_id: string;
  school_id: string;
  active: number;
};
export const demoEnabled = import.meta.env.VITE_SCHOOL_AGENT_DEMO === "1";
export const demoNotice = "시연용 계정 — 실제 인증 아님 · 가상 데이터";

export async function wakeServer(
  signal: AbortSignal,
  {
    fetcher = fetch,
    timeoutMs = 120000,
    intervalMs = 3000,
    requestTimeoutMs = 10000,
  } = {},
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!signal.aborted && Date.now() < deadline) {
    try {
      const response = await fetcher("/api/health", {
        cache: "no-store",
        signal: AbortSignal.any([
          signal,
          AbortSignal.timeout(
            Math.max(1, Math.min(requestTimeoutMs, deadline - Date.now())),
          ),
        ]),
      });
      if (response.ok && (await response.json()).status === "ok") return;
    } catch {
      // Render can return a loading page, fail a request, or time out while waking.
    }
    signal.throwIfAborted();
    const wait = Math.min(intervalMs, deadline - Date.now());
    if (wait > 0)
      await new Promise<void>((resolve, reject) => {
        const abort = () => {
          clearTimeout(timer);
          reject(signal.reason);
        };
        const timer = setTimeout(() => {
          signal.removeEventListener("abort", abort);
          resolve();
        }, wait);
        signal.addEventListener("abort", abort, { once: true });
        if (signal.aborted) abort();
      });
  }
  signal.throwIfAborted();
  throw new Error("서버 준비 시간을 초과했습니다. 잠시 후 다시 시도해 주세요.");
}
