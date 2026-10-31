/** Display aliases for fictional demo identities; never used as authorization keys. */
export const channelName = (value: string) =>
  ({
    phone: "유선전화",
    message: "문자·하이톡 등",
    visit: "방문",
    ieodream: "이어드림",
    homepage: "홈페이지",
    external_transfer: "교육청·국민신문고 이관",
    other: "기타",
  })[value] ?? "기타";
const people: Record<string, string> = {
  admin: "김OO 교장",
  deputy: "이OO 교감",
  "academic-head": "최OO 교무부장",
  "office-head": "박OO 행정실장",
  "life-head": "한OO 생활부장",
  "work-support": "오OO 업무지원",
  teacher: "정OO 교사",
  outsider: "정OO 교사",
  "other-admin": "다른 학교 교장 선생님",
  guardian: "김OO 보호자",
  "other-guardian": "이OO 보호자",
  "foreign-guardian": "다른 학교 보호자",
  "system:inbox": "학교 알림",
};
export const personName = (id: string, fallback?: string) =>
  people[id] ?? fallback ?? id;
export const dutyName = (name: string) => name.replaceAll("생활체육부장", "생활부장").replaceAll("생활인성부장", "생활부장").replaceAll("교무기획부장", "교무부장");
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
