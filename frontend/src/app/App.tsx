import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  Link,
  NavLink,
  Outlet,
  Route,
  Routes,
  useParams,
  useSearchParams,
} from "react-router";
import { ApiClient, ApiError } from "../lib/api/client";
import type {
  CaseDetail,
  CaseSummary,
  Member,
  Page,
  Session,
  Task,
  TimelineEvent,
} from "../lib/api/types";
import { SessionProvider, useScope, useSession } from "./providers";
import { additionalCaseFeatures } from "./feature-registry";
import { Badge, Empty, ErrorNotice, date, label } from "../shared/ui";
import { TeacherTasks } from "../features/teacher-tasks";
import { SchoolSupport } from "../features/school-support";
import { Handover } from "../features/school-support/Handover";
import { Files } from "../features/files";
import { GuardianLinks } from "../features/guardian-links";
import { AgentReview } from "../features/agent-review";
import { Inbox, InboxIndicator } from "../features/inbox";
import { SchoolSettings, SchoolContacts } from "../features/school-settings";

export function App() {
  const [auth, setAuth] = useState<{
    api: ApiClient;
    session: Session;
    id: string;
  } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  if (!auth)
    return (
      <main className="login">
        <section className="login-story">
          <div className="brand">
            함께<span>학교 민원 지원</span>
          </div>
          <h1>
            교사를 혼자
            <br />
            두지 않는 대응.
          </h1>
          <p>
            확인할 일은 명확하게.
            <br />
            필요한 지원은 학교와 함께.
          </p>
          <div className="story-line">
            업무 확인 <span>—</span> 학교 지원 <span>—</span> 함께 마무리
          </div>
        </section>
        <section className="login-form">
          <h2>학교 업무 공간 연결</h2>
          <p>개발 계정으로 업무와 지원 흐름을 확인합니다.</p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (pending) return;
              const form = e.currentTarget;
              const token = String(
                new FormData(form).get("token") ?? "",
              ).trim();
              setPending(true);
              setError(null);
              const api = new ApiClient(token);
              try {
                const session = await api.get<Session>("/api/session");
                form.reset();
                setAuth({ api, session, id: crypto.randomUUID() });
              } catch (err) {
                api.dispose();
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
              개발용 계정 발급 시 받은 토큰을 입력하세요. 계정마다 접근할 수
              있는 업무가 다릅니다.
            </p>
            <button className="primary" disabled={pending}>
              {pending ? "연결 확인 중…" : "업무 공간 열기"}
            </button>
          </form>
          {error ? <ErrorNotice error={error} /> : null}
        </section>
      </main>
    );
  return (
    <SessionProvider
      key={auth.id}
      api={auth.api}
      session={auth.session}
      disconnect={() => setAuth(null)}
    >
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<CaseList />} />
          <Route path="cases" element={<CaseList />} />
          <Route path="my-tasks" element={<MyTasks />} />
          <Route path="inbox" element={<Inbox />} />
          <Route path="school-settings" element={<SchoolSettings />} />
          <Route path="school-contacts" element={<SchoolContacts />} />
          <Route path="cases/:caseId" element={<CaseShell />} />
          <Route
            path="*"
            element={
              <>
                <h1>페이지를 찾을 수 없습니다.</h1>
                <Link to="/cases">사건 목록으로</Link>
              </>
            }
          />
        </Route>
      </Routes>
    </SessionProvider>
  );
}

function Layout() {
  const { session, disconnect } = useSession();
  return (
    <div
      className="workspace"
      onClickCapture={(event) => {
        const target = event.target as HTMLElement;
        if (
          target.closest("a:not(.skip), .tabs button, .account button") &&
          document.querySelector('form[data-dirty="true"]') &&
          !window.confirm(
            "저장하지 않은 입력이 있습니다. 이동하면 입력이 사라집니다. 이동할까요?",
          )
        ) {
          event.preventDefault();
          event.stopPropagation();
        }
      }}
    >
      <a className="skip" href="#content">
        본문으로 이동
      </a>
      <aside className="sidebar">
        <Link className="brand" to="/cases">
          함께<span>학교 민원 지원</span>
        </Link>
        <p className="nav-label">학교 업무</p>
        <nav aria-label="주요 메뉴">
          <NavLink to="/cases">사건 목록</NavLink>
          <NavLink to="/my-tasks">내 확인·상담 요청</NavLink>
          <NavLink to="/inbox">학교 알림 수신함</NavLink>
          <NavLink to="/school-contacts">학교 지원 담당</NavLink>
          {session.role === "ADMIN" ? (
            <NavLink to="/school-settings">학교 지원 설정</NavLink>
          ) : null}
        </nav>
        <div className="sidebar-note">
          <strong>함께 처리하는 원칙</strong>
          <p>
            업무 수행자와 사건 총괄을 구분하고, 지원 요청의 확인 과정을
            남깁니다.
          </p>
        </div>
        <div className="account">
          <strong>{session.user_id}</strong>
          <span>
            {label(session.role)} · {session.school_id}
          </span>
          <button onClick={disconnect}>계정 연결 해제</button>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <span>학교 대응 업무 공간</span>
          <InboxIndicator />
          <span className="dev-label">개발 시연</span>
        </header>
        <main id="content" className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function CaseList() {
  const { api } = useSession();
  const scope = useScope();
  const query = useInfiniteQuery({
    queryKey: ["cases", ...scope],
    initialPageParam: "",
    queryFn: ({ pageParam, signal }) =>
      api.get<Page<CaseSummary>>(
        `/api/cases?after=${encodeURIComponent(pageParam)}`,
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const records = query.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>학교의 사건을 함께 살펴봅니다.</h1>
          <p>내가 접근할 수 있는 사건과 현재 총괄을 확인하세요.</p>
        </div>
        <button
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          새로고침
        </button>
      </div>
      <section className="panel">
        <div className="section-heading">
          <h2>사건 목록</h2>
          <span>불러온 사건 {records.length}건</span>
        </div>
        {query.isPending ? (
          <p role="status">사건을 불러오는 중…</p>
        ) : query.error ? (
          <ErrorNotice error={query.error} />
        ) : records.length === 0 ? (
          <Empty>
            접근 가능한 사건이 없습니다. 학교 관리자에게 참여 여부를 확인해
            주세요.
          </Empty>
        ) : (
          <div className="case-list">
            {records.map((c) => (
              <Link
                className="case-row"
                key={c.id}
                to={`/cases/${encodeURIComponent(c.id)}`}
              >
                <div>
                  <span className="meta">{c.id}</span>
                  <h3>{c.title}</h3>
                  <span className="meta">총괄 {c.owner_id}</span>
                </div>
                <Badge value={c.status} />
                <span className="open-label">사건 열기</span>
              </Link>
            ))}
          </div>
        )}
        {query.hasNextPage ? (
          <button
            onClick={() => void query.fetchNextPage()}
            disabled={query.isFetching}
          >
            더 불러오기
          </button>
        ) : null}
      </section>
      <div className="notice">
        접수·분류·근거 답변 기능은 A의 모듈이 연결되면 같은 사건에서 사용할 수
        있습니다.
      </div>
    </>
  );
}

function MyTasks() {
  const { api } = useSession();
  const scope = useScope();
  const query = useInfiniteQuery({
    queryKey: ["my-tasks", ...scope],
    initialPageParam: "",
    queryFn: ({ pageParam, signal }) =>
      api.get<Page<Task & { case_title: string }>>(
        `/api/my/tasks?after=${encodeURIComponent(pageParam)}`,
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const tasks = query.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>내 확인·상담 요청</h1>
          <p>요청 내용을 확인하고 사건에서 회신하세요.</p>
        </div>
        <button
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          새로고침
        </button>
      </div>
      <section className="panel">
        {query.isPending ? (
          <p>불러오는 중…</p>
        ) : query.error ? (
          <ErrorNotice error={query.error} />
        ) : tasks.length === 0 ? (
          <Empty>나에게 배정된 업무가 없습니다.</Empty>
        ) : (
          tasks.map((t) => (
            <Link
              className="case-row"
              key={t.id}
              to={`/cases/${encodeURIComponent(t.case_id)}`}
            >
              <div>
                <p className="meta">
                  {t.case_title} · {label(t.type)}
                </p>
                {t.due_at ? (
                  <p className="meta">완료 기한 {date(t.due_at)}</p>
                ) : null}
                <h3>{t.question}</h3>
              </div>
              <Badge value={t.status} />
            </Link>
          ))
        )}
        {query.hasNextPage ? (
          <button
            disabled={query.isFetching}
            onClick={() => void query.fetchNextPage()}
          >
            더 불러오기
          </button>
        ) : null}
      </section>
    </>
  );
}

function CaseShell() {
  const { caseId = "" } = useParams();
  const { api, session } = useSession();
  const scope = useScope();
  const [search, setSearch] = useSearchParams();
  const requestedTab = search.get("tab") ?? "tasks";
  const knownTabs = [
    "tasks",
    "support",
    "handover",
    "timeline",
    "files",
    "agent-review",
    ...(session.role === "ADMIN" ? ["guardians"] : []),
    ...additionalCaseFeatures.map((feature) => feature.id),
  ];
  const tab = knownTabs.includes(requestedTab) ? requestedTab : "tasks";
  const query = useQuery({
    queryKey: ["case", ...scope, caseId],
    queryFn: ({ signal }) =>
      api.get<CaseDetail>(`/api/cases/${encodeURIComponent(caseId)}`, signal),
  });
  const members = useQuery({
    queryKey: ["members", ...scope, caseId],
    queryFn: ({ signal }) =>
      api.get<Member[]>(
        `/api/cases/${encodeURIComponent(caseId)}/members`,
        signal,
      ),
  });
  if (query.isPending) return <p role="status">사건을 불러오는 중…</p>;
  if (
    !query.data ||
    (query.error instanceof ApiError &&
      [401, 403, 404].includes(query.error.status))
  )
    return (
      <ErrorNotice error={query.error}>
        <Link to="/cases">사건 목록으로</Link>
      </ErrorNotice>
    );
  const record = query.data;
  const feature = additionalCaseFeatures.find((f) => f.id === tab);
  const tabs = [
    { id: "tasks", title: "교사 업무" },
    { id: "support", title: "학교 지원" },
    { id: "handover", title: "총괄·인계" },
    { id: "timeline", title: "처리 이력" },
    { id: "files", title: "사건 자료" },
    { id: "agent-review", title: "AI 지원 검토" },
    ...(session.role === "ADMIN"
      ? [{ id: "guardians", title: "보호자 연결" }]
      : []),
    ...additionalCaseFeatures,
  ];
  return (
    <>
      <Link className="back" to="/cases">
        사건 목록
      </Link>
      <div className="page-heading">
        <div>
          <p className="meta">{record.id}</p>
          <h1>{record.title}</h1>
        </div>
        <button
          disabled={query.isFetching}
          onClick={() => {
            void query.refetch();
            void members.refetch();
          }}
        >
          최신 내용 조회
        </button>
      </div>
      <div className="case-context">
        <Badge value={record.status} />
        <span>
          사건 총괄 <strong>{record.owner_id}</strong>
        </span>
        <span>
          학교 <strong>{record.school_id}</strong>
        </span>
      </div>
      {query.isRefetchError ? <ErrorNotice error={query.error} /> : null}
      {members.error ? <ErrorNotice error={members.error} /> : null}
      <nav className="tabs" aria-label="사건 메뉴">
        {tabs.map((t) => (
          <button
            aria-current={tab === t.id ? "page" : undefined}
            key={t.id}
            onClick={(event) => {
              setSearch({ tab: t.id });
              event.currentTarget.scrollIntoView({
                block: "nearest",
                inline: "nearest",
              });
            }}
          >
            {t.title}
          </button>
        ))}
      </nav>
      <section className="panel" key={`${caseId}-${tab}`}>
        {tab === "tasks" ? (
          <TeacherTasks record={record} members={members.data ?? []} />
        ) : tab === "support" ? (
          <SchoolSupport record={record} members={members.data ?? []} />
        ) : tab === "handover" ? (
          <Handover record={record} members={members.data ?? []} />
        ) : tab === "timeline" ? (
          <Timeline caseId={caseId} />
        ) : tab === "files" ? (
          <Files
            caseId={caseId}
            version={record.version}
            closed={record.status === "CLOSED"}
          />
        ) : tab === "agent-review" ? (
          <AgentReview record={record} />
        ) : tab === "guardians" && session.role === "ADMIN" ? (
          <GuardianLinks
            caseId={caseId}
            version={record.version}
            closed={record.status === "CLOSED"}
          />
        ) : feature ? (
          <feature.Component caseId={caseId} />
        ) : null}
      </section>
    </>
  );
}

function Timeline({ caseId }: { caseId: string }) {
  const { api } = useSession();
  const scope = useScope();
  const query = useQuery({
    queryKey: ["timeline", ...scope, caseId],
    queryFn: ({ signal }) =>
      api.get<TimelineEvent[]>(
        `/api/cases/${encodeURIComponent(caseId)}/timeline`,
        signal,
      ),
  });
  return (
    <>
      <h2>함께 처리한 이력</h2>
      {query.isPending ? (
        <p>이력을 불러오는 중…</p>
      ) : query.error ? (
        <ErrorNotice error={query.error} />
      ) : (
        <ol className="timeline">
          {query.data?.map((e) => (
            <li key={e.id}>
              <div>
                <strong>{label(e.action)}</strong>
                <span>{date(e.created_at)}</span>
              </div>
              <p>
                {e.actor_id === "system:inbox" ? "학교 알림" : e.actor_id} ·
                기록 {e.new_version}
              </p>
              {typeof e.payload.reason === "string" ? (
                <p className="preserve">{e.payload.reason}</p>
              ) : null}
              {typeof e.payload.reply === "string" ? (
                <blockquote className="preserve">{e.payload.reply}</blockquote>
              ) : null}
              {typeof e.payload.result === "string" ? (
                <blockquote className="preserve">{e.payload.result}</blockquote>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </>
  );
}
