import { test, expect } from "@playwright/test";

test("versioned originals, configurable repeat review and reversible same-school relations", async ({
  page,
  request,
}, info) => {
  await page.goto("/cases/demo-case?tab=documents");
  await page
    .getByRole("button", { name: "학교 관리자 관리자 · admin", exact: true })
    .click();
  await page.getByText("새 원문·증거 기록", { exact: true }).click();
  const createForm = page.locator("form").filter({
    has: page.getByRole("button", { name: "원문 기록 저장", exact: true }),
  });
  await createForm
    .getByLabel("자료 제목", { exact: true })
    .fill("[가상] 재문의 원문");
  await createForm
    .getByLabel("원문·정정 내용", { exact: true })
    .fill("[가상] 답변을 받지 못했다는 주장");
  await createForm
    .getByLabel("출처·확인 경위", { exact: true })
    .fill("[가상] 수동 접수");
  await createForm
    .getByLabel("기록 대상 시각 (한국 시간)", { exact: true })
    .fill("2026-10-29T10:00");
  await createForm
    .getByRole("button", { name: "원문 기록 저장", exact: true })
    .click();
  const article = page.getByRole("article").filter({
    has: page.getByRole("heading", {
      name: "[가상] 재문의 원문 · 접수 원문",
      exact: true,
    }),
  });
  await expect(article).toBeVisible();
  await article.getByText("정정 버전 추가", { exact: true }).click();
  const appendForm = article.locator("form");
  await appendForm
    .getByLabel("원문·정정 내용", { exact: true })
    .fill("[가상] 이전 답변 이후 새 증거를 제시한 문의로 정정");
  await appendForm
    .getByLabel("출처·확인 경위", { exact: true })
    .fill("[가상] 이전 접수와 대조");
  await appendForm
    .getByLabel("기록 대상 시각 (한국 시간)", { exact: true })
    .fill("2026-10-30T10:00");
  await appendForm
    .getByRole("button", { name: "정정 버전 저장", exact: true })
    .click();
  await expect(
    article.getByText("최신 버전 2", { exact: false }),
  ).toBeVisible();
  await article.getByText("모든 버전 대조", { exact: true }).click();
  await expect(
    article.getByText("[가상] 답변을 받지 못했다는 주장", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "반복·새 사실", exact: true }).click();
  await page.getByText("학교의 반복·지연 검토 기준", { exact: true }).click();
  await page.getByLabel("비교 기간 (일)", { exact: true }).fill("40");
  await page
    .getByLabel("재확인 건수 (현재 사건 포함)", { exact: true })
    .fill("2");
  await page
    .getByLabel("답변 기록 재확인 기준 (시간, 선택)", { exact: true })
    .fill("24");
  await page
    .getByRole("button", { name: "반복 검토 기준 저장", exact: true })
    .click();
  await expect(
    page.getByText("학교 검토 기준: 40일 · 2건.", { exact: false }),
  ).toBeVisible();
  await page.getByText("동일인·동일 사안 비교 코드", { exact: true }).click();
  await page
    .getByLabel("동일인 구분 코드", { exact: true })
    .fill("sample-person");
  await page
    .getByLabel("동일 사안 구분 코드", { exact: true })
    .fill("sample-issue");
  await page
    .getByLabel("접수 시각 (한국 시간)", { exact: true })
    .fill("2026-10-30T10:00");
  await page
    .getByRole("button", { name: "비교 코드 저장", exact: true })
    .click();
  await page
    .getByRole("button", { name: "원문 대조: comparison-example", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "[가상] 비교용 이전 문의", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("연결·분리 사유", { exact: true })
    .fill("[가상] 동일 사안 자료를 함께 대조하기 위해 연결");
  await page
    .getByRole("button", { name: "연결·분리 판단 저장", exact: true })
    .click();
  await expect(
    page.getByText("comparison-example · 연결 검토됨", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "검토 결과", exact: true })
    .selectOption("SEPARATED");
  await page
    .getByLabel("연결·분리 사유", { exact: true })
    .fill("[가상] 새 증거에 따른 별도 쟁점으로 분리");
  await page
    .getByRole("button", { name: "연결·분리 판단 저장", exact: true })
    .click();
  await expect(
    page.getByText("comparison-example · 별도 사건으로 분리", { exact: false }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("case-comparison-mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "AI 지원 검토", exact: true }).click();
  await page.getByText("함께 검토할 원문 버전 선택", { exact: true }).click();
  await page.getByLabel("[가상] 재문의 원문 · 버전 1", { exact: true }).check();
  await page.getByLabel("[가상] 재문의 원문 · 버전 2", { exact: true }).check();
  await expect(
    page.getByRole("button", { name: "AI 지원 검토 시작", exact: true }),
  ).toBeDisabled();
  const login = await request.post("/api/demo/login", {
    data: { account: "admin" },
  });
  const auth = { Authorization: `Bearer ${(await login.json()).token}` };
  const versions = await (
    await request.get("/api/cases/demo-case/documents", { headers: auth })
  ).json();
  expect(
    versions.filter(
      (item: { label: string }) => item.label === "[가상] 재문의 원문",
    ),
  ).toHaveLength(2);
});

test("human support decision records cited observations, revisions and stale report checks", async ({
  page,
  request,
}, info) => {
  const login = await request.post("/api/demo/login", {
    data: { account: "admin" },
  });
  const auth = { Authorization: `Bearer ${(await login.json()).token}` };
  await page.goto("/cases/demo-case?tab=support-decisions");
  await page
    .getByRole("button", { name: "학교 관리자 관리자 · admin", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "학교의 지원 판단", exact: true }),
  ).toBeVisible();
  const fill = async (reason: string) => {
    await page.getByLabel("판단 사유·변경 사유", { exact: true }).fill(reason);
    await page
      .getByLabel("지원 대상", { exact: true })
      .fill("[가상] 담당 교사와 학교 대응팀");
    await page
      .getByLabel("지원 경로·담당 역할", { exact: true })
      .fill("[가상] 학교 관리자 공동 검토");
    await page
      .getByLabel("남은 학교 업무", { exact: true })
      .fill("[가상] 이전 답변 전달 여부 확인");
    await page
      .getByLabel("관찰 1 구분", { exact: true })
      .selectOption("UNVERIFIED");
    await page
      .getByLabel("관찰 1 내용", { exact: true })
      .fill("[가상] 원문 확인 전이므로 미응답 여부는 미확인");
    await page
      .getByRole("button", { name: "지원 판단 저장", exact: true })
      .click();
  };
  await fill("[가상] 추가 확인 후 학교 내 지원 경로 검토");
  await expect(
    page.getByRole("heading", { name: "추가 검토 · 판단 1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("현재 사건과 일치하는 최신 판단입니다.", { exact: true }),
  ).toBeVisible();
  const first = (
    await (
      await request.get("/api/cases/demo-case/support-decisions", {
        headers: auth,
      })
    ).json()
  )[0];
  expect(
    (
      await request.get(
        `/api/support-decisions/${first.decision_id}/snapshot?expected_case_version=${first.recorded_case_version}`,
        { headers: auth },
      )
    ).status(),
  ).toBe(200);
  await page.getByText("검토 후 새 판단 기록", { exact: true }).click();
  await fill("[가상] 새 확인 사항을 반영해 판단을 갱신");
  await expect(
    page.getByRole("heading", { name: "추가 검토 · 판단 2", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("이후 새 판단이 기록되었습니다.", { exact: false }),
  ).toBeVisible();
  const latest = (
    await (
      await request.get("/api/cases/demo-case/support-decisions", {
        headers: auth,
      })
    ).json()
  )[0];
  expect(
    (
      await request.get(
        `/api/support-decisions/${first.decision_id}/snapshot?expected_case_version=${latest.recorded_case_version}`,
        { headers: auth },
      )
    ).status(),
  ).toBe(409);
  const task = await request.post("/api/cases/demo-case/tasks", {
    headers: { ...auth, "Idempotency-Key": crypto.randomUUID() },
    data: {
      expected_version: latest.recorded_case_version,
      type: "FOLLOW_UP",
      assignee_id: "teacher",
      question: "[가상] 판단 이후 사실 확인",
    },
  });
  expect(task.status()).toBe(201);
  await page
    .getByRole("button", { name: "최신 내용 조회", exact: true })
    .click();
  await expect(
    page.getByText("이 판단 이후 사건이 변경되었습니다.", { exact: false }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: info.outputPath("support-decisions-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "계정 연결 해제" }).click();
  await page
    .getByRole("button", { name: "담당 교사 교사 · teacher", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "지원 판단", exact: true }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("heading", { name: "학교의 지원 판단", exact: true }),
  ).not.toBeVisible();
});

test("Render waking page retries HTML and errors before offering fictional accounts", async ({
  page,
}, info) => {
  let checks = 0;
  await page.route("**/api/health", async (route) => {
    checks++;
    if (checks === 1)
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "Render loading",
      });
    else if (checks === 2) await route.fulfill({ status: 503, body: "waking" });
    else await route.continue();
  });
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText(
    "서버를 준비하고 있습니다",
  );
  await expect(
    page.getByRole("button", {
      name: "학교 관리자 관리자 · admin",
      exact: true,
    }),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("note")).toContainText(
    "시연용 계정 — 실제 인증 아님 · 가상 데이터",
  );
  expect(checks).toBe(3);
  await page.screenshot({
    path: info.outputPath("demo-login.png"),
    fullPage: true,
  });
});

test("real demo account login and switching clears staff data before another school or guardian", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "학교 관리자 관리자 · admin", exact: true })
    .click();
  await page.getByRole("link", { name: /demo-case/ }).click();
  await expect(
    page.getByRole("heading", { name: "[가상] 상담 지원 사례", exact: true }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "학교 관리자 관리자 · admin", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "[가상] 상담 지원 사례", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "계정 연결 해제" }).click();
  await page
    .getByRole("button", {
      name: "다른 학교 관리자 관리자 · other-admin",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", { name: "[가상] 상담 지원 사례", exact: true }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "계정 연결 해제" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "사건 목록", exact: true })
    .first()
    .click();
  await expect(
    page.getByText("접근 가능한 사건이 없습니다.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "계정 연결 해제" }).click();
  await page
    .getByRole("button", { name: "보호자 보호자 · guardian", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "보호자 시연 공간" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toContainText(
    "현재 연결된 가상 사건이 없습니다",
  );
  await expect(
    page.getByText("학교 지원 설정", { exact: true }),
  ).not.toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: info.outputPath("guardian-demo-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "계정 연결 해제" }).click();
  await expect(
    page.getByRole("button", {
      name: "학교 관리자 관리자 · admin",
      exact: true,
    }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("404 demo discovery preserves the original token form", async ({
  page,
  request,
}) => {
  const issued = await request.post("/api/demo/login", {
    data: { account: "admin" },
  });
  expect(issued.ok()).toBe(true);
  await page.route("**/api/demo/accounts", (route) =>
    route.fulfill({ status: 404, body: "{}" }),
  );
  await page.goto("/");
  await page.getByLabel("개발 세션 토큰").fill((await issued.json()).token);
  await page
    .getByRole("button", { name: "업무 공간 열기", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "계정 연결 해제" }),
  ).toBeVisible();
});

test("wake-up gives up after two minutes and retry can succeed", async ({
  page,
}) => {
  let ready = false;
  await page.clock.install();
  await page.route("**/api/health", (route) =>
    ready ? route.continue() : route.fulfill({ status: 503, body: "sleeping" }),
  );
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText("서버를 준비");
  await page.clock.runFor(121000);
  await expect(
    page.getByRole("button", { name: "다시 시도", exact: true }),
  ).toBeVisible();
  ready = true;
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "학교 관리자 관리자 · admin",
      exact: true,
    }),
  ).toBeVisible();
});

test("cross-case proposal, human review and report dependency use the same recorded sources", async ({
  page,
  request,
}, info) => {
  await page.goto("/cases/demo-case?tab=comparison");
  await page
    .getByRole("button", { name: "학교 관리자 관리자 · admin", exact: true })
    .click();
  await page
    .getByLabel("직접 비교할 사건 ID", { exact: true })
    .fill("comparison-example");
  await page.getByRole("button", { name: "사건 대조", exact: true }).click();
  await page.getByText("비교할 원문·업무 선택", { exact: true }).click();
  await page
    .getByLabel("demo-case · [가상] 재문의 원문 · 버전 2", { exact: true })
    .check();
  await page
    .getByLabel("comparison-example · [가상] 이전 접수 · 버전 1", {
      exact: true,
    })
    .check();
  await page
    .getByRole("button", { name: "선택한 자료로 비교 준비", exact: true })
    .click();
  await page
    .getByRole("button", { name: "AI 사건 비교 시작", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "AI 비교 제안 · 검토 대기",
      exact: true,
    }),
  ).toBeVisible({ timeout: 10000 });
  await expect(
    page.getByText("규칙/검증용 결과 — 실제 모델 호출 아님", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("AI 검토 사유", { exact: true })
    .fill("[가상] 원문 대조 후 제안 검토");
  await page
    .getByRole("button", { name: "AI 제안 검토 기록", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "검토한 AI 관찰을 사람 기록에 불러오기",
      exact: true,
    })
    .click();
  await page
    .getByLabel("비교 검토 사유", { exact: true })
    .fill("[가상] 두 사건의 자료와 답변 기록을 함께 대조함");
  await page
    .getByRole("listbox", { name: "비교 관찰 1 출처", exact: true })
    .selectOption(["demo-case", "comparison-example"]);
  const ai = page.getByRole("combobox", {
    name: "참고한 검토 완료 AI (선택)",
    exact: true,
  });
  await expect(ai.locator("option")).toHaveCount(2);
  await ai.selectOption({ index: 1 });
  await page
    .getByRole("button", { name: "사람의 비교 검토 저장", exact: true })
    .click();
  await expect(
    page.getByText("현재 사건과 일치하는 비교 검토입니다.", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("cross-case-review-mobile.png"),
    fullPage: true,
  });
  const login = await request.post("/api/demo/login", {
    data: { account: "admin" },
  });
  const auth = { Authorization: `Bearer ${(await login.json()).token}` };
  const review = (
    await (
      await request.get("/api/cases/demo-case/comparison-reviews", {
        headers: auth,
      })
    ).json()
  )[0];
  await page.getByRole("button", { name: "지원 판단", exact: true }).click();
  await page.getByText("검토 후 새 판단 기록", { exact: true }).click();
  await page
    .getByLabel("판단 사유·변경 사유", { exact: true })
    .fill("[가상] 사람의 교차 비교 검토를 지원 판단에 참조");
  await page.getByLabel("지원 대상", { exact: true }).fill("[가상] 담당 교사");
  await page
    .getByLabel("지원 경로·담당 역할", { exact: true })
    .fill("[가상] 학교 공동 검토");
  await page
    .getByLabel("남은 학교 업무", { exact: true })
    .fill("[가상] 실제 답변 전달 확인");
  await page
    .getByRole("combobox", { name: "관찰 1 출처", exact: true })
    .selectOption(`COMPARISON_REVIEW:${review.id}`);
  await page
    .getByLabel("관찰 1 내용", { exact: true })
    .fill("[가상] 비교 기록상 추가 증빙 확인 필요");
  await page
    .getByRole("button", { name: "지원 판단 저장", exact: true })
    .click();
  await expect(
    page.getByText("현재 사건과 일치하는 최신 판단입니다.", { exact: true }),
  ).toBeVisible();
  const decision = (
    await (
      await request.get("/api/cases/demo-case/support-decisions", {
        headers: auth,
      })
    ).json()
  )[0];
  const related = await (
    await request.get("/api/cases/comparison-example", { headers: auth })
  ).json();
  expect(
    (
      await request.post("/api/cases/comparison-example/tasks", {
        headers: { ...auth, "Idempotency-Key": crypto.randomUUID() },
        data: {
          expected_version: related.version,
          type: "FOLLOW_UP",
          assignee_id: "teacher",
          question: "[가상] 비교 사건의 후속 확인",
        },
      })
    ).status(),
  ).toBe(201);
  await page
    .getByRole("button", { name: "판단 이력 새로고침", exact: true })
    .click();
  await expect(
    page.getByText("현재 사건과 일치하는 최신 판단입니다.", { exact: true }),
  ).not.toBeVisible();
  expect(
    (
      await request.get(
        `/api/support-decisions/${decision.decision_id}/snapshot?expected_case_version=${decision.current_case_version}`,
        { headers: auth },
      )
    ).status(),
  ).toBe(409);
});

test("a concurrent change preserves the unsaved comparison text while blocking old inputs", async ({
  page,
  request,
}) => {
  await page.goto("/cases/demo-case?tab=comparison");
  await page
    .getByRole("button", { name: "학교 관리자 관리자 · admin", exact: true })
    .click();
  await page
    .getByLabel("직접 비교할 사건 ID", { exact: true })
    .fill("comparison-example");
  await page.getByRole("button", { name: "사건 대조", exact: true }).click();
  await page
    .getByRole("button", { name: "선택한 자료로 비교 준비", exact: true })
    .click();
  await page
    .getByLabel("비교 검토 사유", { exact: true })
    .fill("[가상] 충돌 후에도 보존할 검토 사유");
  await page
    .getByLabel("비교 관찰 1 내용", { exact: true })
    .fill("[가상] 원문을 대조 중이며 아직 확인되지 않은 관찰");
  const issued = await request.post("/api/demo/login", {
    data: { account: "admin" },
  });
  const auth = { Authorization: `Bearer ${(await issued.json()).token}` };
  const related = await (
    await request.get("/api/cases/comparison-example", { headers: auth })
  ).json();
  expect(
    (
      await request.post("/api/cases/comparison-example/tasks", {
        headers: { ...auth, "Idempotency-Key": crypto.randomUUID() },
        data: {
          expected_version: related.version,
          type: "FACT_CHECK",
          assignee_id: "teacher",
          question: "[가상] 동시에 추가된 사실 확인",
        },
      })
    ).status(),
  ).toBe(201);
  await page
    .getByRole("button", { name: "사람의 비교 검토 저장", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "현재 자료로 비교를 다시 준비하세요",
  );
  await expect(page.getByLabel("비교 검토 사유", { exact: true })).toHaveValue(
    "[가상] 충돌 후에도 보존할 검토 사유",
  );
  await expect(
    page.getByLabel("비교 관찰 1 내용", { exact: true }),
  ).toHaveValue("[가상] 원문을 대조 중이며 아직 확인되지 않은 관찰");
});
