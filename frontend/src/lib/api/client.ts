export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
    public uncertain = false,
  ) {
    super(message);
  }
}
export type Command = {
  path: string;
  method: "POST" | "PATCH";
  key: string;
  body: Readonly<Record<string, unknown>>;
};
export const command = (
  path: string,
  body: Record<string, unknown>,
  method: Command["method"] = "POST",
): Command => ({
  path,
  method,
  key: crypto.randomUUID(),
  body: Object.freeze({ ...body }),
});

export class ApiClient {
  private controller = new AbortController();
  constructor(
    private token: string,
    private fetcher: typeof fetch = (input, init) => fetch(input, init),
    private timeoutMs = 15000,
  ) {}
  dispose() {
    this.controller.abort();
  }
  async get<T>(path: string, signal?: AbortSignal): Promise<T> {
    return this.request(path, { method: "GET" }, signal);
  }
  async execute<T>(cmd: Command): Promise<T> {
    return this.request(cmd.path, {
      method: cmd.method,
      body: JSON.stringify(cmd.body),
      headers: {
        "Idempotency-Key": cmd.key,
        "Content-Type": "application/json",
      },
    });
  }
  async upload<T>(path: string, file: Blob, key: string): Promise<T> {
    return this.request(path, {
      method: "POST",
      body: file,
      headers: {
        "Content-Type": "application/octet-stream",
        "Idempotency-Key": key,
      },
    });
  }
  async download(path: string): Promise<Blob> {
    return this.request<Blob>(path, { method: "GET" }, undefined, true);
  }
  private async request<T>(
    path: string,
    init: RequestInit,
    signal?: AbortSignal,
    binary = false,
  ): Promise<T> {
    if (!path.startsWith("/api/"))
      throw new Error("API 경로는 /api/로 시작해야 합니다.");
    const signals = [
      this.controller.signal,
      AbortSignal.timeout(this.timeoutMs),
      ...(signal ? [signal] : []),
    ];
    let response: Response;
    try {
      response = await this.fetcher(path, {
        ...init,
        cache: "no-store",
        headers: { ...init.headers, Authorization: `Bearer ${this.token}` },
        signal: AbortSignal.any(signals),
      });
    } catch {
      throw new ApiError(
        0,
        "NETWORK_ERROR",
        "서버 응답을 확인하지 못했습니다. 연결을 확인한 뒤 다시 조회해 주세요.",
        undefined,
        init.method !== "GET",
      );
    }
    if (response.ok && binary) {
      try {
        return (await response.blob()) as T;
      } catch {
        throw new ApiError(
          0,
          "DOWNLOAD_INTERRUPTED",
          "다운로드가 중단되었습니다. 다시 시도해 주세요.",
        );
      }
    }
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const fallback: Record<number, string> = {
        401: "세션이 만료되었습니다. 토큰을 다시 연결해 주세요.",
        403: "이 작업에 접근할 권한이 없습니다.",
        404: "사건이나 대상을 찾을 수 없습니다.",
        409: "다른 변경이 있습니다. 최신 내용을 확인해 주세요.",
        422: "입력 항목을 확인해 주세요.",
      };
      throw new ApiError(
        response.status,
        data?.code ?? "HTTP_ERROR",
        data?.message ??
          fallback[response.status] ??
          "요청을 처리하지 못했습니다.",
        data?.request_id ?? response.headers.get("X-Request-ID") ?? undefined,
      );
    }
    if (data === null)
      throw new ApiError(
        response.status,
        "INVALID_RESPONSE",
        "서버 응답 형식을 확인할 수 없습니다.",
        undefined,
        init.method !== "GET",
      );
    return data as T;
  }
}
