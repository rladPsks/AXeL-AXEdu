import { describe, expect, it } from "vitest";
import { recommendSupport, type SupportContact } from "./recommendations";

const contacts: SupportContact[] = ["교장", "교감", "행정실장", "생활부장", "교무부장", "업무지원"].map((label, index) => ({ id: String(index), label, user_id: String(index), substitute_id: null, support_contact_id: String(index) }));
const eligible = contacts.map((c) => c.user_id);
describe("support recommendations", () => {
  it("prioritizes school coordination for infringement concerns", () => {
    const result = recommendSupport({ classification: { infringement_flags: ["REVIEW"] }, routing: null }, contacts, eligible);
    expect(result.map((r) => r.role)).toEqual(["교감", "교장", "생활부장"]);
  });
  it("routes administrative issues to the office head", () => {
    expect(recommendSupport({ classification: { category: "ADMIN" }, routing: null }, contacts, eligible)[0].role).toBe("행정실장");
  });
  it("normalizes legacy roles and excludes unavailable users", () => {
    const intake = { classification: {}, routing: { action_role: "HEAD_LIFE_PE", role_labels: { HEAD_LIFE_PE: "생활체육부장" } } };
    expect(recommendSupport(intake, contacts, eligible)[0].role).toBe("생활부장");
    expect(recommendSupport(intake, contacts, eligible.filter((id) => id !== "3")).some((r) => r.user_id === "3")).toBe(false);
  });
  it("resolves substitutes without duplicate recommendations", () => {
    const substituted = contacts.map((c) => c.label === "교장" ? { ...c, support_contact_id: "1" } : c);
    const result = recommendSupport({ classification: { urgency: "HIGH" }, routing: null }, substituted, eligible);
    expect(result.filter((r) => r.user_id === "1")).toHaveLength(1);
    expect(recommendSupport(undefined, contacts, eligible)).toEqual([]);
  });
});
