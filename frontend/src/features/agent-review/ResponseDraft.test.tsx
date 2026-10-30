import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ResponseDraft } from "./ResponseDraft";

describe("stored review compatibility", () => {
  it("renders historical results without pretending checks were performed", () => {
    const html = renderToStaticMarkup(<ResponseDraft result={{}} />);
    expect(html).toContain("이전 결과에는 답변 초안이 없습니다.");
    expect(html).toContain("저장된 점검 결과가 없습니다.");
  });
  it("renders current draft, checks and evidence", () => {
    const html = renderToStaticMarkup(<ResponseDraft result={{
      response_draft: "검토용 초안", validation_checks: ["확인 필요"], evidence_used: ["official-1"],
    }} />);
    expect(html).toContain("검토용 초안");
    expect(html).toContain("확인 필요");
    expect(html).toContain("official-1");
  });
});
