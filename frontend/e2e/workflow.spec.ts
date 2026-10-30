import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const file = process.env.SCHOOL_E2E_CREDENTIALS;
if (!file)
  throw new Error(
    "SCHOOL_E2E_CREDENTIALS must point to isolated test credentials",
  );
const tokens = JSON.parse(readFileSync(file, "utf8")).tokens as Record<
  string,
  string
>;
const guardianTokens = JSON.parse(readFileSync(file, "utf8"))
  .guardian_tokens as Record<string, string>;
async function connect(page: Page, user: string) {
  await page.getByLabel("개발 세션 토큰").fill(tokens[user]);
  await page.getByRole("button", { name: "업무 공간 열기" }).click();
  await expect(
    page.getByRole("button", { name: "계정 연결 해제" }),
  ).toBeVisible();
}
async function switchTo(page: Page, user: string) {
  await page.getByRole("button", { name: "계정 연결 해제" }).click();
  await connect(page, user);
}

test("real server: task, conflict, support, timeline, handover and account isolation", async ({
  page,
  request,
}) => {
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await page.goto("/cases");
  await connect(page, "admin");
  await page
    .getByRole("link")
    .filter({ hasText: "[가상] 상담 지원 사례" })
    .click();
  await page
    .getByRole("combobox", { name: "수행자", exact: true })
    .selectOption("teacher");
  await page
    .getByLabel("확인할 내용")
    .fill("[가상] 상담 가능 일정을 확인해 주세요.");
  await page.getByRole("button", { name: "업무 요청 보내기" }).click();
  await expect(
    page.getByText("수행자 teacher", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".case-context")).toContainText("admin");
  await page.screenshot({
    path: "test-results/admin-case.png",
    fullPage: true,
  });
  await switchTo(page, "teacher");
  await expect(
    page.getByRole("heading", { name: "[가상] 상담 지원 사례" }),
  ).toBeVisible();
  await page.getByLabel("회신 내용").fill("[가상] 화요일 상담 가능");
  // Another authorized command makes the teacher's current snapshot stale.
  const current = await request.get("/api/cases/demo-case", {
    headers: { Authorization: `Bearer ${tokens.admin}` },
  });
  const version = (await current.json()).version;
  const concurrent = await request.post(
    "/api/cases/demo-case/support-requests",
    {
      headers: {
        Authorization: `Bearer ${tokens.admin}`,
        "Idempotency-Key": crypto.randomUUID(),
      },
      data: {
        expected_version: version,
        coordinator_id: "admin",
        type: "JOINT_RESPONSE",
        reason: "[가상] 동시 수정 검사",
      },
    },
  );
  expect(concurrent.status()).toBe(201);
  await page.getByRole("button", { name: "회신 저장" }).click();
  await expect(page.getByRole("alert")).toContainText("최신 사건");
  await expect(page.getByLabel("회신 내용")).toHaveValue(
    "[가상] 화요일 상담 가능",
  );
  await page
    .getByRole("button", { name: "최신 내용 확인 후 입력 계속" })
    .click();
  await page.getByRole("button", { name: "회신 저장" }).click();
  await expect(page.locator("blockquote")).toContainText(
    "[가상] 화요일 상담 가능",
  );
  await page.getByRole("button", { name: "학교 지원", exact: true }).click();
  await page
    .getByRole("combobox", { name: "지원 담당", exact: true })
    .selectOption("admin");
  await page.getByLabel("필요한 지원").fill("[가상] 상담 동석을 요청합니다.");
  await page.getByRole("button", { name: "지원 요청 보내기" }).click();
  await expect(
    page.getByText("[가상] 상담 동석을 요청합니다.", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/teacher-support.png",
    fullPage: true,
  });
  await switchTo(page, "admin");
  await page.getByRole("button", { name: "학교 지원", exact: true }).click();
  const support = page
    .locator("article")
    .filter({ hasText: "[가상] 상담 동석을 요청합니다." });
  await support.getByRole("button", { name: "지원 처리 저장" }).click();
  await expect(support.locator(".badge")).toHaveText("확인함");
  await support.getByLabel("처리 상태").selectOption("COMPLETED");
  await support.getByLabel("지원 내용·결과").fill("[가상] 동석 완료");
  await support.getByRole("button", { name: "지원 처리 저장" }).click();
  await expect(support.locator("blockquote")).toHaveText("[가상] 동석 완료");
  await page.getByRole("button", { name: "총괄·인계", exact: true }).click();
  await page.getByLabel("인수할 관리자").selectOption("deputy");
  await page.getByLabel("인계 사유").fill("[가상] 부재 대체");
  await page.getByRole("button", { name: "총괄 인계 요청" }).click();
  await expect(page.locator(".case-context")).toContainText("admin");
  await expect(page.getByText("인수 대기", { exact: true })).toBeVisible();
  await switchTo(page, "deputy");
  await page.getByRole("button", { name: "총괄·인계", exact: true }).click();
  await page.getByRole("button", { name: "총괄 인수 수락" }).click();
  await expect(page.locator(".case-context")).toContainText("deputy");
  await page.getByRole("button", { name: "처리 이력", exact: true }).click();
  await expect(page.getByText("인계 수락", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/mobile-timeline.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await switchTo(page, "outsider");
  await expect(page.getByRole("alert")).toContainText("권한");
  await page.getByRole("link", { name: "사건 목록으로" }).click();
  await expect(
    page.getByText("접근 가능한 사건이 없습니다.", { exact: false }),
  ).toBeVisible();
  expect(failures).toEqual([]);
});

test("unsaved navigation is cancellable and a lost response replays one saved command", async ({
  page,
  request,
}) => {
  await page.goto("/cases/demo-case");
  await connect(page, "admin");
  const before = await request.get("/api/cases/demo-case", {
    headers: { Authorization: `Bearer ${tokens.admin}` },
  });
  const version = (await before.json()).version;
  await page
    .getByRole("combobox", { name: "수행자", exact: true })
    .selectOption("teacher");
  await page.getByLabel("확인할 내용").fill("[가상] 네트워크 재시도 확인");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "학교 지원", exact: true }).click();
  await expect(page.getByLabel("확인할 내용")).toHaveValue(
    "[가상] 네트워크 재시도 확인",
  );
  const sent: { key: string; body: string | null }[] = [];
  await page.route(
    "**/api/cases/demo-case/tasks",
    async (route) => {
      sent.push({
        key: route.request().headers()["idempotency-key"],
        body: route.request().postData(),
      });
      const response = await route.fetch();
      expect(response.status()).toBe(201);
      await route.abort("failed"); // DB commit happened but the browser never saw the response.
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "업무 요청 보내기" }).click();
  await expect(
    page.getByRole("button", { name: "같은 요청 다시 확인" }),
  ).toBeVisible();
  await page.route(
    "**/api/cases/demo-case/tasks",
    async (route) => {
      sent.push({
        key: route.request().headers()["idempotency-key"],
        body: route.request().postData(),
      });
      await route.continue();
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "같은 요청 다시 확인" }).click();
  await expect(
    page.getByText("[가상] 네트워크 재시도 확인", { exact: true }),
  ).toBeVisible();
  expect(sent).toHaveLength(2);
  expect(sent[0]).toEqual(sent[1]);
  const after = await request.get("/api/cases/demo-case", {
    headers: { Authorization: `Bearer ${tokens.admin}` },
  });
  const result = await after.json();
  expect(result.version).toBe(version + 1);
  expect(
    result.tasks.filter(
      (t: { question: string }) => t.question === "[가상] 네트워크 재시도 확인",
    ),
  ).toHaveLength(1);
});

test("private file upload/download and verified guardian revocation use the real server", async ({
  page,
  request,
}, testInfo) => {
  await page.goto("/cases/demo-case");
  await connect(page, "admin");
  await page.getByRole("button", { name: "사건 자료", exact: true }).click();
  await page
    .getByLabel("파일", { exact: true })
    .setInputFiles({
      name: "private-note.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("[fictional] private note"),
    });
  await page
    .getByRole("combobox", { name: "열람 범위", exact: true })
    .selectOption("RESTRICTED");
  const uploaded = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/api/cases/demo-case/files?"),
  );
  await page.getByRole("button", { name: "자료 저장", exact: true }).click();
  const response = await uploaded;
  expect(response.status()).toBe(201);
  const fileId = (await response.json()).file_id;
  await expect(
    page.getByText("private-note.txt", { exact: true }),
  ).toBeVisible();
  const saved = page.waitForEvent("download");
  await page.getByRole("button", { name: "다운로드", exact: true }).click();
  const download = await saved;
  const output = testInfo.outputPath("downloaded-note.txt");
  await download.saveAs(output);
  expect(readFileSync(output, "utf8")).toBe("[fictional] private note");
  await page.screenshot({
    path: testInfo.outputPath("private-files.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "보호자 연결", exact: true }).click();
  await page.getByText("확인한 보호자 연결", { exact: true }).click();
  await page.getByLabel("확인된 보호자 계정 ID").fill("guardian");
  await page.getByLabel("학교의 관계 확인 근거").fill("[가상] 학교 대면 확인");
  await page.getByRole("button", { name: "관계 확인 후 연결" }).click();
  await expect(page.getByText("관계 확인됨", { exact: true })).toBeVisible();
  const parentHeaders = { Authorization: `Bearer ${guardianTokens.guardian}` };
  const access = await request.get("/api/guardian/cases/demo-case/access", {
    headers: parentHeaders,
  });
  expect(access.status()).toBe(200);
  expect(await access.json()).toEqual({
    case_id: "demo-case",
    relationship_verified: true,
  });
  expect(
    (
      await request.get("/api/cases/demo-case", { headers: parentHeaders })
    ).status(),
  ).toBe(401);
  await page.getByLabel("해제 사유").fill("[가상] 관계 종료");
  await page
    .getByRole("button", { name: "보호자 연결 해제", exact: true })
    .click();
  await expect(page.getByText("연결 해제됨", { exact: true })).toBeVisible();
  expect(
    (
      await request.get("/api/guardian/cases/demo-case/access", {
        headers: parentHeaders,
      })
    ).status(),
  ).toBe(404);
  await switchTo(page, "teacher");
  await page.getByRole("button", { name: "사건 자료", exact: true }).click();
  await expect(
    page.getByText("등록한 자료가 없습니다.", { exact: true }),
  ).toBeVisible();
  expect(
    (
      await request.get(`/api/files/${fileId}/download`, {
        headers: { Authorization: `Bearer ${tokens.teacher}` },
      })
    ).status(),
  ).toBe(403);
  await page.getByRole("button", { name: "AI 지원 검토", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "AI 지원 검토 시작" }),
  ).toBeDisabled();
  await expect(
    page.getByText("OpenAI 연결 설정이 준비되지 않았습니다.", { exact: false }),
  ).toBeVisible();
});
