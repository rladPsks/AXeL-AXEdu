import { test, expect } from "@playwright/test";

test("opening a seeded complaint searches real evidence and supports refresh", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/cases");
  await page.getByRole("button", { name: "김갑수 교장 관리자", exact: true }).click();
  await page.locator('a.case-row[href="/cases/demo-multilingual-zh"]').click();
  const rag = page.getByRole("region", { name: "공식 근거 RAG 검색" });
  await expect(rag.getByRole("heading", { name: /공식 근거 RAG 검색 · [1-4]건/ })).toBeVisible();
  await expect(rag.getByText("저장된 근거가 없어 현재 접수 내용으로 실제 검색했습니다.")).toBeVisible();
  await expect(rag.getByText(/출처:/).first()).toBeVisible();
  const response = page.waitForResponse(r => r.url().endsWith("/intake/rag-search") && r.request().method() === "POST");
  await rag.getByRole("button", { name: "RAG 근거 다시 검색", exact: true }).click();
  expect((await response).status()).toBe(200);
  await expect(rag.getByText("저장했습니다.")).toBeVisible();
  await expect(rag.getByText("접수 내용을 바탕으로 검색한 공식 문서 결과입니다.")).toBeVisible();
  expect(errors).toEqual([]);
});
