import { chromium, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";

await mkdir("test-results/feedback", { recursive: true });
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
await page.goto(process.env.FEEDBACK_BASE_URL ?? "http://127.0.0.1:5175");
await expect(page.locator('[aria-label="역할 선택"] > button')).toHaveCount(3);
await expect(page.locator(".landing-art")).toBeVisible();
await page.screenshot({
  path: "test-results/feedback/landing-v2.png",
  fullPage: true,
});
await page.setViewportSize({ width: 390, height: 844 });
await page.screenshot({
  path: "test-results/feedback/landing-mobile-v2.png",
  fullPage: true,
});
expect(
  await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
).toBe(true);
await page.setViewportSize({ width: 1440, height: 1100 });
await page
  .getByRole("button", { name: "김○○ 교장 관리자", exact: true })
  .click();
await expect(
  page.getByRole("heading", { name: "학교 민원을 함께 살펴봅시다" }),
).toBeVisible();
await expect(
  page.getByRole("heading", { name: "전체 민원 목록", exact: true }),
).toBeVisible();
await expect(page.getByLabel("학교 민원 안내")).toBeVisible();
await expect(page.getByLabel("민원 단계별 현황")).toBeVisible();
expect(await page.locator("body").innerText()).not.toContain("악성");
expect(
  await page
    .locator(".sidebar")
    .evaluate((el) => getComputedStyle(el).backgroundColor),
).toBe("rgb(255, 246, 226)");
await expect(page.getByRole("img", { name: "함께" })).toBeVisible();
expect(await page.locator("body").innerText()).not.toMatch(
  /\b(admin|teacher|deputy|outsider|demo-case)\b|사건/,
);
await page.screenshot({
  path: "test-results/feedback/list.png",
  fullPage: true,
});
await page.emulateMedia({ colorScheme: "dark" });
await page.screenshot({
  path: "test-results/feedback/list-dark-v2.png",
  fullPage: true,
});
await page.emulateMedia({ colorScheme: "light" });
await page.getByRole("button", { name: "처음 화면", exact: true }).click();
await expect(page.locator('[aria-label="역할 선택"] > button')).toHaveCount(3);
await page.getByRole("button", { name: "김○○ 교장 관리자", exact: true }).click();
await page.locator('.sidebar a.brand').click();
await expect(page.locator('[aria-label="역할 선택"] > button')).toHaveCount(3);
await page.getByRole("button", { name: "김○○ 교장 관리자", exact: true }).click();
await page.getByRole("link", { name: "새 민원 접수", exact: true }).click();
await expect(page.getByPlaceholder("예: 생활지도, 단순 민원 등")).toBeVisible();
await expect(page.getByPlaceholder("예: 김○○, 이○○")).toBeVisible();
await expect(page.locator('input[name="occurred_at"]')).toBeVisible();
await expect(
  page.getByPlaceholder("예: ○○○○년 ○월 ○일, ○○ 관련 민원 발생"),
).toBeVisible();
await expect(
  page.getByRole("button", { name: "민원 접수하고 전송하기" }),
).toBeVisible();
await expect(
  page.getByText(
    "※ 접수한 민원은 담당자와 교장·교감 선생님(민원대응팀)에게 전송돼요.",
  ),
).toBeVisible();
await page.screenshot({
  path: "test-results/feedback/intake.png",
  fullPage: true,
});
await page.getByRole("link", { name: "학교 지원 담당", exact: true }).click();
await expect(page.locator(".contact-card")).toHaveCount(4);
await page.screenshot({
  path: "test-results/feedback/contacts.png",
  fullPage: true,
});
await page.getByRole("link", { name: "학교 지원 설정", exact: true }).click();
await expect(
  page.getByRole("heading", { name: "부재와 업무 대리 담당" }),
).toBeVisible();
await expect(
  page.getByRole("combobox", { name: "민원대응팀", exact: true }),
).toBeVisible();
await expect(
  page.getByLabel("지원 확인 요청 알림 기준 (분)", { exact: true }),
).toBeVisible();
await expect(
  page.getByLabel("기한이 지난 뒤 다시 알려드릴 시간 (분)", { exact: true }),
).toBeVisible();
await expect(page.locator(".team-node")).toHaveCount(5);
expect(await page.locator("body").innerText()).not.toMatch(
  /\b(admin|teacher|deputy|outsider|demo-case)\b|대체|사건/,
);
await page
  .getByRole("combobox", { name: "민원대응팀", exact: true })
  .selectOption("deputy");
await page.getByRole("button", { name: "학교 기준 저장", exact: true }).click();
await expect(page.getByText("저장했습니다.", { exact: false })).toBeVisible();
await expect(
  page.getByRole("combobox", { name: "민원대응팀", exact: true }),
).toHaveValue("deputy");
await page.screenshot({
  path: "test-results/feedback/settings.png",
  fullPage: true,
});
await page.getByRole("link", { name: "활동·지원 현황", exact: true }).click();
await expect(
  page.getByText(
    "발생한 민원에 대하여 필요한 지원 방안을 확인하기 위한 화면입니다.",
  ),
).toBeVisible();
expect(await page.locator("body").innerText()).not.toMatch(
  /교사 순위|소진 진단|직접 응대로 세지/,
);
await page.getByRole("button", { name: "계정 연결 해제" }).click();
await page.getByRole("button", { name: "최○○ 교사 교사", exact: true }).click();
await page.getByRole("link", { name: "민원 목록", exact: true }).click();
await expect(
  page.getByRole("heading", { name: "민원 목록", exact: true }),
).toBeVisible();
await expect(
  page.getByText("아직 나에게 연결된 민원이 없어요.", { exact: false }),
).toBeVisible();
expect(await page.locator(".case-row").count()).toBe(0);
expect(errors).toEqual([]);
await browser.close();
console.log(
  "Feedback UI checks passed: names, role-scoped lists, intake guidance, contacts, team chart, settings submission, dashboard.",
);
