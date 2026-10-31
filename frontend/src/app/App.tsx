import { caseName, schoolName } from "../shared/names";
import { personName } from "../shared/names";
import { Brand } from "../shared/Brand";
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
  useNavigate,
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
import { Entry, GuardianDemo } from "./Entry";
import { demoEnabled, demoNotice, type GuardianSession } from "./demo";
import { SupportDecisions } from "../features/support-decisions";
import { CaseComparison, CaseDocuments } from "../features/case-comparison";
import { ActivityLog } from "../features/activity-log";
import { Recordings } from "../features/recordings";
import { DashboardPage } from "../features/dashboard";
import { IntakeCreate } from "../features/intake";

import { PatternsPage, FullHistory, WorkProduct } from "../features/mission";

export function App() {
  const [auth, setAuth] = useState<{
    api: ApiClient;
    session: Session;
    id: string;
  } | null>(null);
  const [guardian, setGuardian] = useState<{
    api: ApiClient;
    session: GuardianSession;
  } | null>(null);
  if (guardian)
    return (
      <GuardianDemo
        api={guardian.api}
        session={guardian.session}
        disconnect={() => setGuardian(null)}
      />
    );
  if (!auth)
    return (
      <Entry
        onStaff={(api, session) =>
          setAuth({ api, session, id: crypto.randomUUID() })
        }
        onGuardian={(api, session) => setGuardian({ api, session })}
      />
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
          <Route path="intake" element={<IntakeCreate />} />
          <Route path="my-tasks" element={<MyTasks />} />
          <Route path="inbox" element={<Inbox />} />
          <Route path="patterns" element={<PatternsPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="school-settings" element={<SchoolSettings />} />
          <Route path="school-contacts" element={<SchoolContacts />} />
          <Route path="cases/:caseId" element={<CaseShell />} />
          <Route
            path="*"
            element={
              <>
                <h1>페이지를 찾을 수 없습니다.</h1>
                <Link to="/cases">민원 목록으로</Link>
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
  const navigate = useNavigate();
  const goHome = () => {
    disconnect();
    navigate("/");
  };
  return (
    <div
      className="workspace"
      onClickCapture={(event) => {
        const target = event.target as HTMLElement;
        if (
          target.closest(
            "a:not(.skip), .tabs button, .account button, .home-button",
          ) &&
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
        <Link className="brand" to="/" onClick={disconnect}>
          <Brand />
          <span>학교 민원 지원</span>
        </Link>
        <p className="nav-label">학교 업무</p>
        <nav aria-label="주요 메뉴">
          <NavLink to="/cases">
            {session.role === "ADMIN" ? "전체 민원 목록" : "민원 목록"}
          </NavLink>

          <NavLink to="/intake">새 민원 접수</NavLink>
          <NavLink to="/my-tasks">내 확인·상담 요청</NavLink>
          <NavLink to="/inbox">학교 알림 수신함</NavLink>
          <NavLink to="/school-contacts">학교 지원 담당</NavLink>
          {session.role === "ADMIN" ? (
            <NavLink to="/school-settings">학교 지원 설정</NavLink>
          ) : null}
          {session.role === "ADMIN" ? (
            <><NavLink to="/patterns">민원인·반복 누적 패턴</NavLink><NavLink to="/dashboard">교사 노출도·처리시간</NavLink></>
          ) : null}
        </nav>
        <div className="sidebar-note">
          <strong>학교 민원, 함께 처리해요</strong>
          <p>혼자 받지 않고, 함께 보고, 기록으로 남깁니다.</p>
        </div>
        <div className="account">
          <strong>{personName(session.user_id)}</strong>
          <span>
            {label(session.role)} · {schoolName(session.school_id)}
          </span>
          <button onClick={goHome}>계정 연결 해제</button>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <span className="topbar-user">
            <strong>{personName(session.user_id)}</strong> ·{" "}
            {schoolName(session.school_id)}
          </span>
          <InboxIndicator />
          <button className="home-button" onClick={goHome}>
            처음 화면
          </button>
        </header>
        <main id="content" className="content">
          {demoEnabled ? (
            <p className="demo-notice" role="note">
              {demoNotice}
            </p>
          ) : null}
          <Outlet />
          <footer className="copyright">© 2026 AXeL. All rights reserved.</footer>
        </main>
      </div>
    </div>
  );
}

const stageLabels = {
  simple: "단순",
  review: "살펴보기",
  together: "함께 대응",
};
const channelLabels: Record<string, string> = {
  phone: "유선전화",
  message: "문자·하이톡 등",
  visit: "방문",
  ieodream: "이어드림",
  homepage: "홈페이지",
  external_transfer: "교육청·국민신문고 이관",
  other: "기타",
};

function CaseList() {
  const { api, session } = useSession();
  const scope = useScope();
  const query = useInfiniteQuery({
    queryKey: ["cases", ...scope],
    initialPageParam: "",
    queryFn: ({ pageParam, signal }) =>
      api.get<Page<CaseSummary>>(
        `/api/cases?after=${encodeURIComponent(pageParam)}${demoEnabled ? "&order=demo" : ""}`,
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const records = query.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>학교 민원을 함께 살펴봅시다</h1>
          <p>
            {session.role === "ADMIN"
              ? "우리 학교 민원과 필요한 지원을 확인해요."
              : "나에게 온 민원과 함께할 지원 담당을 확인해요."}
          </p>
        </div>
        <button
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          새로고침
        </button>
      </div>
      <section className="stage-tiles" aria-label="민원 단계별 현황">
        {(["simple", "review", "together"] as const).map((stage) => (
          <div className={`stage-tile stage-${stage}`} key={stage}>
            <span>{stageLabels[stage]}</span>
            <strong>
              {query.isPending
                ? "—"
                : records.filter((c) => c.stage === stage).length}
            </strong>
          </div>
        ))}
      </section>
      <p className="tile-scope">
        불러온 민원 기준 · 분류 전 {records.filter((c) => !c.stage).length}건
      </p>
      <aside className="complaint-guide" aria-label="학교 민원 안내">
        <p>
          <strong>학교생활의 문의와 요청을 함께 살펴요</strong>생활지도·상담,
          학적, 시설, 행정 안내 등
        </p>
        <p className="conduct-guide">
          <strong>혼자 감당하지 말고 함께 대응해요</strong>욕설·협박·반복적인
          모욕은 민원대응팀과 확인해요.
        </p>
      </aside>
      <section className="panel">
        <div className="section-heading case-list-heading">
          <h2>{session.role === "ADMIN" ? "전체 민원 목록" : "민원 목록"}</h2>
          <span
            className={`scope-badge ${session.role === "ADMIN" ? "scope-all" : "scope-mine"}`}
          >
            {session.role === "ADMIN" ? "학교 전체" : "나에게 온 민원"}
          </span>
          <span>불러온 민원 {records.length}건</span>
        </div>
        {query.isPending ? (
          <p role="status">민원을 불러오는 중…</p>
        ) : query.error ? (
          <ErrorNotice error={query.error} />
        ) : records.length === 0 ? (
          <Empty>
            아직 나에게 연결된 민원이 없어요. 도움이 필요하면 교장·교감 선생님께
            알려 주세요.
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
                  <span className={`stage-badge ${c.stage ?? "pending"}`}>
                    {c.stage ? stageLabels[c.stage] : "분류 전"}
                  </span>
                  <h3>{c.title}</h3>
                  <span className="meta">
                    {c.channel
                      ? (channelLabels[c.channel] ?? "기타")
                      : "접수 경로 확인 전"}{" "}
                    ·{" "}
                    {c.received_at ? date(c.received_at) : "접수 일시 확인 전"}{" "}
                    · 기본 담당 {personName(c.owner_id)}
                  </span>
                </div>
                <Badge value={c.status} />
                <span className="open-label">민원 열기</span>
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
          <p>요청 내용을 확인하고 민원에서 회신하세요.</p>
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
  const requestedTab = search.get("tab") ?? "intake";
  const knownTabs = [
    "tasks",
    "support",
    "handover",
    "timeline",
    "files",
    "agent-review",
    "activities",
    "recordings",
    ...(session.role === "ADMIN"
      ? ["guardians", "support-decisions", "documents", "comparison", "patterns", "report", "response", "translation"]
      : []),
    ...additionalCaseFeatures.map((feature) => feature.id),
  ];
  const tab = knownTabs.includes(requestedTab) ? requestedTab : "intake";
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
  if (query.isPending) return <p role="status">민원을 불러오는 중…</p>;
  if (
    !query.data ||
    (query.error instanceof ApiError &&
      [401, 403, 404].includes(query.error.status))
  )
    return (
      <ErrorNotice error={query.error}>
        <Link to="/cases">민원 목록으로</Link>
      </ErrorNotice>
    );
  const record = query.data;
  const feature = additionalCaseFeatures.find((f) => f.id === tab);
  const tabs = [
    { id: "intake", title: "① 원문·분류·검토" },
    { id: "tasks", title: "② 담당자 전달·업무" },
    { id: "support", title: "학교 지원" },
    { id: "handover", title: "총괄·인계" },
    { id: "timeline", title: "처리 이력" },
    { id: "files", title: "민원 자료" },
    { id: "agent-review", title: "AI 지원 검토" },
    { id: "activities", title: "활동 기록" },
    { id: "recordings", title: "동의 녹취" },
    ...(session.role === "ADMIN"
      ? [
          { id: "patterns", title: "민원인·누적 패턴" },
          { id: "response", title: "답변 초안·승인" },
          { id: "report", title: "교육지원청 이관 서류" },
          { id: "translation", title: "다국어 원문 대조" },
          { id: "guardians", title: "보호자 연결" },
          { id: "support-decisions", title: "지원 판단" },
          { id: "documents", title: "원문·답변" },
          { id: "comparison", title: "반복·새 사실" },
        ]
      : []),
    ...additionalCaseFeatures.filter((f) => f.id !== "intake"),
  ];
  return (
    <>
      <Link className="back" to="/cases">
        민원 목록
      </Link>
      <div className="page-heading">
        <div>
          <p className="meta">{caseName(record.id)}</p>
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
          기본 담당 <strong>{personName(record.owner_id)}</strong>
        </span>
        <span>
          학교 <strong>{schoolName(record.school_id)}</strong>
        </span>
      </div>
      {query.isRefetchError ? <ErrorNotice error={query.error} /> : null}
      {members.error ? <ErrorNotice error={members.error} /> : null}
      <nav className="tabs mission-tabs" aria-label="민원 메뉴">
        {tabs
          .filter((t) => ["intake", "tasks", "support", "response", "patterns", "timeline", "report"].includes(t.id))
          .map((t) => (
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
      <details
        className="case-more"
        open={!["intake", "tasks", "support", "response", "patterns", "timeline", "report"].includes(tab)}
      >
        <summary>자료·이력·기타 기능</summary>
        <nav className="tabs" aria-label="민원 부가 기능">
          {tabs
            .filter((t) => !["intake", "tasks", "support", "response", "patterns", "timeline", "report"].includes(t.id))
            .map((t) => (
              <button
                key={t.id}
                aria-current={tab === t.id ? "page" : undefined}
                onClick={() => setSearch({ tab: t.id })}
              >
                {t.title}
              </button>
            ))}
        </nav>
      </details>
      <section className="panel" key={`${caseId}-${tab}`}>
        {tab === "tasks" ? (
          <TeacherTasks record={record} members={members.data ?? []} />
        ) : tab === "support" ? (
          <SchoolSupport record={record} members={members.data ?? []} />
        ) : tab === "handover" ? (
          <Handover record={record} members={members.data ?? []} />
        ) : tab === "timeline" ? (
          session.role === "ADMIN" ? <FullHistory caseId={caseId} /> : <Timeline caseId={caseId} />
        ) : tab === "files" ? (
          <Files
            caseId={caseId}
            version={record.version}
            closed={record.status === "CLOSED"}
          />
        ) : tab === "agent-review" ? (
          <AgentReview record={record} />
        ) : tab === "activities" ? (
          <ActivityLog record={record} members={members.data ?? []} />
        ) : tab === "recordings" ? (
          <Recordings record={record} />
        ) : tab === "support-decisions" && session.role === "ADMIN" ? (
          <SupportDecisions record={record} />
        ) : tab === "documents" && session.role === "ADMIN" ? (
          <CaseDocuments record={record} />
        ) : tab === "comparison" && session.role === "ADMIN" ? (
          <CaseComparison record={record} />
        ) : tab === "patterns" && session.role === "ADMIN" ? (
          <PatternsPage caseId={caseId} />
        ) : ["response", "report", "translation"].includes(tab) && session.role === "ADMIN" ? (
          <WorkProduct record={record} kind={tab === "report" ? "REPORT" : tab === "translation" ? "TRANSLATION" : "RESPONSE"} />
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
                {e.actor_id === "system:inbox"
                  ? "학교 알림"
                  : personName(e.actor_id)}{" "}
                · 기록 {e.new_version}
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
