import { test, expect } from "@playwright/test";

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
