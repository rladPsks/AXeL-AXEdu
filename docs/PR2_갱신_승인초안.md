# 기존 PR #2 제목·설명 갱신 초안

대상: https://github.com/rladPsks/AXeL-AXEdu/pull/2

코드는 d8a171e로 기존 개발 브랜치에 push 완료했다. 아래는 자동 승인 검토가 차단한 PR 메타데이터 갱신의 검토용 초안이다. 병합이나 실제 계정 변경은 포함하지 않는다.

## 제목

Build B shared foundation, teacher support and school coordination

## 설명

교사 업무·학교 지원·총괄 인계를 공통 React/FastAPI 기반에서 처리하고, 일정·재배정·부재 대체·학교 설정·앱 알림까지 연결합니다. B의 기준 계약 v1.3과 OpenAPI를 제공해 A가 동일 사건·권한·버전 체계에 기능을 연결할 수 있게 합니다.

- 학교/사건 권한, 버전 충돌·멱등 처리, atomic 감사 기록, checksum migration 및 공통 React shell/API client.
- 교사 업무·지원·인계 수락/거절/취소, 일정 사유 기록과 재배정, 부재/미확인 대체와 앱 알림 outbox·재시도·사용자 확인. 총괄은 인계 수락 시만 변경됩니다.
- 사용자 승인 범위의 기존 학교 구성원 권한/활성 관리: 자기 변경 금지, 남은 책임 검사, 대상 세션 폐기와 감사의 원자성. 실제 계정 변경 없이 가상 DB에서 검증했습니다.
- 비공개 파일·보호자 관계 검사·공통 AI 실행 원장/worker/검토/복구·OpenAI Responses adapter. 제한 파일/관계 이력의 교사 노출도 검사합니다.

검증: Python 서버 69개, 프론트 10개, 실제 서버 Playwright 6개 통과. Production build와 git diff --check 통과. 브라우저 검증은 로컬 Edge에서 수행했습니다.

남은 범위: 실제 기관 인증/보호자 본인 확인, 실제 OpenAI 호출·품질 검증(로컬 키/모델 필요), A 접수·원문·종결 guard/handler 연결, 반복 비교·사람의 지원 결정·보고서 연계, 동의 녹취/STT, 활동 대시보드. 앱 수신함을 제공하며 이메일/SMS는 연결하지 않습니다. 전체 제품 완료나 운영 배포 승인을 의미하지 않습니다.

연결 문서: docs/개발자_AB_통합계약_확정_v1.md 및 docs/B_일정_학교설정_알림_연결안내.md. Draft 상태로 검토하며 병합하지 않습니다.
