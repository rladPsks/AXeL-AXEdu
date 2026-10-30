import { describe, it, expect } from "vitest";
import { koreanTime, localInput } from "./dates";
describe("Korean school schedule times", () => {
  it("converts an explicit Korean civil time to UTC", () =>
    expect(koreanTime("2026-11-01T10:30")).toBe("2026-11-01T01:30:00.000Z"));
  it("displays UTC as a Korean datetime input independently of browser timezone", () =>
    expect(localInput("2026-11-01T01:30:00Z")).toBe("2026-11-01T10:30"));
  it("preserves unspecified dates as null or empty form values", () => {
    expect(koreanTime(null)).toBeNull();
    expect(localInput(null)).toBe("");
  });
});
