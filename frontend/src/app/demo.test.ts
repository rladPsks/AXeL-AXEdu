import { afterEach, expect, it, vi } from "vitest";
import { wakeServer } from "./demo";

afterEach(() => vi.useRealTimers());

it("waits through a proxy loading page and HTTP failure until real health JSON", async () => {
  vi.useFakeTimers();
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response("loading"))
    .mockResolvedValueOnce(new Response("unavailable", { status: 503 }))
    .mockResolvedValueOnce(Response.json({ status: "ok" }));
  const pending = wakeServer(new AbortController().signal, {
    fetcher,
    intervalMs: 1000,
  });
  await vi.advanceTimersByTimeAsync(2000);
  await pending;
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(fetcher.mock.calls[0][0]).toBe("/api/health");
});

it("stops at the total deadline and can be explicitly retried", async () => {
  vi.useFakeTimers();
  const fetcher = vi.fn().mockRejectedValue(new Error("offline"));
  const outcome = wakeServer(new AbortController().signal, {
    fetcher,
    timeoutMs: 5000,
    intervalMs: 1000,
  }).catch((error: Error) => error);
  await vi.advanceTimersByTimeAsync(5000);
  expect(await outcome).toBeInstanceOf(Error);
  expect(fetcher).toHaveBeenCalledTimes(5);
  await wakeServer(new AbortController().signal, {
    fetcher: vi.fn().mockResolvedValue(Response.json({ status: "ok" })),
  });
});

it("aborts retries on unmount without another request", async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  const fetcher = vi.fn().mockRejectedValue(new Error("offline"));
  const outcome = wakeServer(controller.signal, { fetcher }).catch(
    (error: Error) => error,
  );
  await vi.advanceTimersByTimeAsync(1);
  controller.abort();
  await outcome;
  await vi.advanceTimersByTimeAsync(20000);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
