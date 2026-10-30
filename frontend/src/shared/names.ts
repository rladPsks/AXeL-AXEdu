/** Display aliases for fictional demo identities; never used as authorization keys. */
const people: Record<string, string> = {
  admin: "김○○ 교장",
  deputy: "이○○ 교감",
  teacher: "최○○ 교사",
  outsider: "정○○ 교사",
  "other-admin": "다른 학교 교장 선생님",
  guardian: "김○○ 보호자",
  "other-guardian": "이○○ 보호자",
  "foreign-guardian": "다른 학교 보호자",
  "system:inbox": "학교 알림",
};
export const personName = (id: string, fallback?: string) =>
  people[id] ?? fallback ?? id;
export const caseName = (id: string) =>
  ({
    "demo-case": "상담 지원 민원",
    "comparison-example": "이전 상담 민원",
  })[id] ?? `민원 접수번호 ${id}`;
export const schoolName = (id: string) =>
  ({
    "demo-school": "함께초등학교",
    "other-school": "이웃초등학교",
  })[id] ?? id;
