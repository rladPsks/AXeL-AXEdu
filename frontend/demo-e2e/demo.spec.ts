import { test, expect } from "@playwright/test";

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
