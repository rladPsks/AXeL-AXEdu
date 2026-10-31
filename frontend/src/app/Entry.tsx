import { personName, schoolName } from "../shared/names";
import { Brand } from "../shared/Brand";
import { useEffect, useState } from "react";
import { ApiClient } from "../lib/api/client";
import type { Session } from "../lib/api/types";
import { ErrorNotice } from "../shared/ui";
import {
  demoEnabled,
  demoNotice,
  wakeServer,
  type DemoAccount,
  type GuardianSession,
} from "./demo";

export function Entry({
  onStaff,
  onGuardian,
}: {
  onStaff: (api: ApiClient, session: Session) => void;
  onGuardian: (api: ApiClient, session: GuardianSession) => void;
}) {
  const [accounts, setAccounts] = useState<DemoAccount[] | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">(
    demoEnabled ? "loading" : "ready",
  );
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  useEffect(() => {
    if (!demoEnabled) return;
    const controller = new AbortController();
    setState("loading");
    setError(null);
    void (async () => {
      try {
        await wakeServer(controller.signal);
        const response = await fetch("/api/demo/accounts", {
          cache: "no-store",
          signal: AbortSignal.any([
            controller.signal,
            AbortSignal.timeout(15000),
          ]),
        });
        if (response.status === 404) setAccounts(null);
        else {
          if (!response.ok)
            throw new Error(
              "시연 계정을 불러오지 못했습니다. 다시 시도해 주세요.",
            );
          const data: unknown = await response.json();
          if (
            !Array.isArray(data) ||
            !data.every(
              (item) =>
                typeof item.id === "string" &&
                typeof item.name === "string" &&
                ["STAFF", "GUARDIAN"].includes(item.kind),
            )
          ) {
            throw new Error("시연 계정 응답을 확인하지 못했습니다.");
          }
          setAccounts(data as DemoAccount[]);
        }
        if (!controller.signal.aborted) setState("ready");
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err);
          setState("failed");
        }
      }
    })();
    return () => controller.abort();
  }, [attempt]);

  async function connect(token: string, kind: DemoAccount["kind"] = "STAFF") {
    const api = new ApiClient(token);
    try {
      if (kind === "GUARDIAN")
        onGuardian(
          api,
          await api.get<GuardianSession>("/api/guardian/session"),
        );
      else {
        onStaff(api, await api.get<Session>("/api/session"));
      }
    } catch (err) {
      api.dispose();
      throw err;
    }
  }
  async function login(account: DemoAccount) {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const response = await fetch("/api/demo/login", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account: account.id }),
        signal: AbortSignal.timeout(15000),
      });
      if (!response.ok)
        throw new Error(
          "시연 계정에 연결하지 못했습니다. 다시 선택하거나 서버 준비를 다시 시도해 주세요.",
        );
      const result = await response.json();
      if (typeof result.token !== "string")
        throw new Error("세션 응답을 확인하지 못했습니다.");
      await connect(result.token, account.kind);
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  }
  const tokenForm = (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        if (pending) return;
        const form = event.currentTarget;
        const token = String(new FormData(form).get("token") ?? "").trim();
        setPending(true);
        setError(null);
        try {
          await connect(token);
          form.reset();
        } catch (err) {
          setError(err);
        } finally {
          setPending(false);
        }
      }}
    >
      <label>
        개발 세션 토큰
        <input
          type="password"
          name="token"
          required
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <p className="hint">
        개발용 계정 발급 시 받은 토큰을 입력하세요. 계정마다 접근할 수 있는
        업무가 다릅니다.
      </p>
      <button className="primary" disabled={pending}>
        {pending ? "연결 확인 중…" : "업무 공간 열기"}
      </button>
    </form>
  );
  const featured =
    accounts?.filter(
      (a) =>
        a.kind === "STAFF" && ["admin", "deputy", "office-head", "academic-head", "teacher"].includes(a.id),
    ) ?? [];
  const roleCard = (account: DemoAccount) => (
    <button
      className="role-card"
      aria-label={`${personName(account.id, account.name)} ${account.kind === "GUARDIAN" ? "보호자" : account.role === "ADMIN" ? "관리자" : "교사"}`}
      key={account.id}
      disabled={pending}
      onClick={() => void login(account)}
    >
      <span className="role-avatar" aria-hidden="true">
        {personName(account.id, account.name).slice(0, 1)}
      </span>
      <span>
        <strong>{personName(account.id, account.name)}</strong>
        <small>
          {account.id === "admin"
            ? "학교 전체 민원을 함께 살펴봐요"
            : account.id === "deputy"
              ? "필요한 지원과 담당자를 연결해요"
              : account.role === "TEACHER"
                ? "나에게 온 민원과 지원을 확인해요"
                : "함께 쓰는 업무 공간으로 들어가요"}
        </small>
      </span>
    </button>
  );
  return (
    <main className="entry-v2">
      <section className="entry-copy">
        <div className="brand">
          <Brand />
        </div>
        <h1>학교 민원, <span className="accent">함께</span> 처리해요</h1>
        <p>우리 학교 민원대응팀이 함께 쓰는 공간이에요.</p>
        {state === "loading" ? (
          <p role="status">학교 업무 공간을 준비하고 있어요…</p>
        ) : state === "failed" ? (
          <button onClick={() => setAttempt((v) => v + 1)}>다시 시도</button>
        ) : accounts ? (
          <>
            <div className="role-cards" aria-label="역할 선택">
              {featured.map(roleCard)}
            </div>
            {accounts.length === 0 ? (
              <p>현재 사용할 수 있는 계정이 없어요.</p>
            ) : null}
            <div className="entry-tools">
              <details>
                <summary>기존 토큰으로 연결</summary>
                {tokenForm}
              </details>
            </div>
          </>
        ) : (
          tokenForm
        )}
        {error ? <ErrorNotice error={error} /> : null}
        {demoEnabled ? (
          <p className="demo-notice" role="note">
            {demoNotice}
          </p>
        ) : null}
      </section>
      <img
        className="landing-art"
        src="/brand/umbrella_teacher.svg"
        alt="우산 아래 함께하는 선생님"
        width="760"
        height="660"
      />
      <footer className="copyright">© 2026 AXeL. All rights reserved.</footer>
    </main>
  );
}

export function GuardianDemo({
  api,
  session,
  disconnect,
}: {
  api: ApiClient;
  session: GuardianSession;
  disconnect: () => void;
}) {
  const [access, setAccess] = useState<"loading" | "allowed" | "unlinked">(
    "loading",
  );
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    const controller = new AbortController();
    void api
      .get("/api/guardian/cases/demo-case/access", controller.signal)
      .then(
        () => setAccess("allowed"),
        (err) => {
          if (!controller.signal.aborted) {
            if (err.status === 404) setAccess("unlinked");
            else setError(err);
          }
        },
      );
    return () => {
      controller.abort();
      api.dispose();
    };
  }, [api]);
  return (
    <main className="content guardian-demo">
      <p className="demo-notice" role="note">
        {demoNotice}
      </p>
      <div className="page-heading">
        <h1>보호자 시연 공간</h1>
        <button onClick={disconnect}>계정 연결 해제</button>
      </div>
      <section className="panel">
        <h2>{personName(session.guardian_id)}</h2>
        <p>학교 {schoolName(session.school_id)}</p>
        {error ? (
          <ErrorNotice error={error} />
        ) : (
          <p role="status">
            {access === "loading"
              ? "민원 연결을 확인하고 있습니다…"
              : access === "allowed"
                ? "가상 민원의 보호자 연결이 확인되었습니다."
                : "현재 연결된 가상 민원이 없습니다. 학교 관리자의 보호자 연결 후 확인할 수 있습니다."}
          </p>
        )}
        <p>
          현재 보호자 시연은 계정 연결과 민원 접근 확인까지 제공합니다. 대외
          답변·접수 화면은 A 모듈 연결 후 사용할 수 있습니다.
        </p>
      </section>
      <footer className="copyright">© 2026 AXeL. All rights reserved.</footer>
    </main>
  );
}
