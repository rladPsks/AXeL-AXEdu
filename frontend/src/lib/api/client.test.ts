import { describe, it, expect, vi } from "vitest";
import { ApiClient, ApiError, command } from "./client";

describe("shared API transport", () => {
  it("preserves binary bytes and idempotency key for upload", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response('{"file_id":"f1"}', { status: 201 }));
    const api = new ApiClient("token", fetcher);
    const file = new Blob(["binary content"]);
    await api.upload(
      "/api/cases/demo/files?filename=note.txt&expected_version=1",
      file,
      "upload-key",
    );
    const options = fetcher.mock.calls[0][1]!;
    expect(options.body).toBe(file);
    expect(options.headers).toMatchObject({
      "Idempotency-Key": "upload-key",
      "Content-Type": "application/octet-stream",
      Authorization: "Bearer token",
    });
  });
  it("downloads through authenticated transport and handles permission errors", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("private note"))
      .mockResolvedValueOnce(
        new Response('{"code":"FILE_FORBIDDEN","message":"권한 없음"}', {
          status: 403,
        }),
      );
    const api = new ApiClient("token", fetcher);
    expect(await (await api.download("/api/files/f1/download")).text()).toBe(
      "private note",
    );
    await expect(api.download("/api/files/f1/download")).rejects.toMatchObject({
      code: "FILE_FORBIDDEN",
      status: 403,
    });
  });
  it("replays an uncertain command with the exact key and body", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("connection lost"))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ version: 2 }), { status: 201 }),
      );
    const api = new ApiClient("secret", fetcher);
    const cmd = command("/api/cases/demo/tasks", {
      expected_version: 1,
      question: "원문",
    });
    await expect(api.execute(cmd)).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      uncertain: true,
    });
    await expect(api.execute(cmd)).resolves.toEqual({ version: 2 });
    const one = fetcher.mock.calls[0][1]!;
    const two = fetcher.mock.calls[1][1]!;
    expect(one.body).toBe(two.body);
    expect(one.headers).toEqual(two.headers);
    expect(one.headers).toMatchObject({
      Authorization: "Bearer secret",
      "Idempotency-Key": cmd.key,
    });
    expect(one.cache).toBe("no-store");
  });
  it("preserves the conflict code and never automatically resends", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "VERSION_CONFLICT",
          message: "다시 조회",
          request_id: "r1",
        }),
        { status: 409 },
      ),
    );
    await expect(
      new ApiClient("token", fetcher).execute(
        command("/api/example", { expected_version: 1 }),
      ),
    ).rejects.toMatchObject({
      status: 409,
      code: "VERSION_CONFLICT",
      requestId: "r1",
      uncertain: false,
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("handles a non-JSON error without reflecting its HTML", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response("<html>upstream secret</html>", { status: 502 }),
      );
    await expect(
      new ApiClient("token", fetcher).get("/api/example"),
    ).rejects.toMatchObject({
      code: "HTTP_ERROR",
      status: 502,
      message: "요청을 처리하지 못했습니다.",
    });
  });
  it("cancels outstanding requests on session disposal", async () => {
    let signal: AbortSignal | null | undefined;
    const fetcher = vi.fn<typeof fetch>(async (_url, options) => {
      signal = options?.signal;
      return new Response("{}");
    });
    const api = new ApiClient("token", fetcher);
    await api.get("/api/session");
    api.dispose();
    expect(signal?.aborted).toBe(true);
  });
  it("a successful non-JSON mutation remains uncertain", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("", { status: 200 }));
    await expect(
      new ApiClient("token", fetcher).execute(command("/api/example", {})),
    ).rejects.toBeInstanceOf(ApiError);
    // A fresh response is required: a consumed stream must never count as success.
    const error = await new ApiClient(
      "token",
      vi.fn<typeof fetch>().mockResolvedValue(new Response("")),
    )
      .execute(command("/api/example", {}))
      .catch((e) => e);
    if (!(error instanceof ApiError)) throw new Error("Expected ApiError");
    expect(error.uncertain).toBe(true);
  });
});
