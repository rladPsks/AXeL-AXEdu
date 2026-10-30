# B 사람의 지원 판단·보고서 참조 연결

2026-10-31, 통합 계약 v1.4 추가 사항. Render 무료 + Vercel 시연 구성을 유지한다. 반복 비교 전체와 A 보고서 구현이 완료된 것은 아니다.

이후 v1.5의 [반복·원문 버전 연결 안내](B_반복비교_원문버전_연결안내.md)에서 DOCUMENT_VERSION 출처를 추가했다. 아래 v1.4 당시 설명보다 추가 계약을 우선한다.

## 구현된 사용자 흐름

관리자가 사건의 **지원 판단** 탭에서 학교 내 지원·전문 지원·외부 지원·추가 검토 중 하나를 선택한다. 판단 사유·대상·경로/담당 역할·남은 학교 업무를 적고, 저장된 출처마다 확인된 사실/당사자 주장/미확인을 구분해 관찰을 남긴다. 기본 관찰 구분은 미확인이다.

선택한 사건·업무·지원·비공개 파일의 저장 시점 내용을 함께 기록한다. 이 기록은 수정·삭제하지 않는다. 변경할 때는 최신 판단 ID를 supersedes_id로 지정한 새 revision을 남긴다. 사건 변경 또는 새 판단 기록 이후의 과거 판단에는 오래된 기록 표시가 붙는다. 과거 snapshot은 그대로 보존한다.

기존 업무·종결·총괄 규칙은 바꾸지 않는다. 판단 기록이 외부 기관 제출·실제 지원 배정·총괄 인계·업무 완료·종결을 대신하지 않는다. 남은 업무의 서술과 당시 미완료 업무/지원 목록을 함께 저장하며 실제 업무 요청과 처리는 기존 탭에서 수행한다. 반복 횟수·감정·신고 표현으로 자동 이관하지 않는다.

## API 계약

모든 경로는 기존 Bearer 인증을 사용한다. 작성·조회·보고서 참조는 같은 학교 ADMIN만 가능하다. 교사·보호자에 대한 대외 DTO는 이 snapshot을 그대로 사용하지 않는다.

| 경로 | 동작 |
|---|---|
| POST /api/cases/{case_id}/support-decisions | 현재 사건 버전과 출처를 확인하고 새 판단 기록 |
| GET /api/cases/{case_id}/support-decisions | 최신 revision부터 과거 이력 조회 |
| GET /api/support-decisions/{decision_id} | 과거 snapshot과 현재 기준 stale/superseded 조회 |
| GET /api/support-decisions/{decision_id}/snapshot?expected_case_version=N | 현재 사건과 일치하는 최신 판단만 보고서 입력으로 제공 |

작성 예시:

```json
{
  "expected_version": 1,
  "decision_type": "KEEP_REVIEWING",
  "reason": "[가상] 이전 응답이 있었는지 추가 확인 필요",
  "target": "담당 교사와 학교 대응팀",
  "route": "학교 관리자 공동 검토",
  "remaining_school_work": "이전 답변 전달 여부 확인",
  "observations": [
    {"source_id": "demo-case", "kind": "UNVERIFIED", "detail": "현재 사건 기본 정보만으로 미응답 여부를 확인할 수 없음"}
  ],
  "input_refs": [{"resource_type": "CASE", "resource_id": "demo-case", "version": 1}],
  "supersedes_id": null,
  "reviewed_run_id": null
}
```

작성은 Idempotency-Key 필수, 사건 OPEN·expected_version·권한·동일 사건 출처·중복 출처·관찰 인용을 검사한다. 성공 시 사건 버전을 1 올린다. 예시에서는 input_case_version=1, recorded_case_version=2가 된다. 작성 자체로 오래된 판단이 되지 않도록 stale은 recorded_case_version과 현재 사건 버전을 비교한다. 동일 키 재시도는 같은 결과를 반환한다. 감사 실패 시 snapshot·사건 버전·멱등 저장 전체를 되돌린다.

출처는 공통 InputRef 계약(CASE/TASK/SUPPORT_REQUEST/FILE)을 따른다. 파일 version은 1, 나머지는 현재 사건 version이다. 같은 사건 자료만 선택할 수 있고 파일 권한을 재확인한다. 일반 AI snapshot과 동일하게 AUDIO는 이 경로에서 사용할 수 없다. 텍스트 파일은 공통 snapshot의 길이 제한/잘림 표시를 유지하고 PDF/이미지는 메타데이터만 저장한다. 실제 내용 대조는 기존 파일 다운로드를 사용한다. 전체 판단 snapshot 상한은 1 MiB다.

판단 사유·관찰·파일 본문은 교사에게 보이는 공통 감사 payload에 넣지 않는다. 공통 감사에는 decision_id와 decision_type만 남긴다. 저장 이력은 DB trigger로 UPDATE/DELETE를 금지하며 기존 적용 migration을 수정하지 않고 새 migration을 추가했다.

## AI 참고와 A 보고서 연결

AI 없이도 사람이 직접 판단을 기록할 수 있다. reviewed_run_id를 사용하면 같은 사건 REVIEW_SUPPORT 실행이 검토 완료(SUCCEEDED)이고 현재 사건 버전에서 사용 가능한지 require_usable_result로 확인한다. AI 생성·검토 완료만으로 지원 판단이 자동 생성되지 않는다. 기록에는 참고한 AI run_id와 당시 제안 결과를 함께 보존한다.

A는 다음 메타데이터를 보고서 원장에 연결해야 한다.

- decision_id, revision, input_case_version, recorded_case_version
- decided_by, created_at, snapshot의 사유·출처·관찰 구분·대상/경로·남은 업무

A의 생성/검토/내보내기에서 오래된 판단이 사용되지 않도록 같은 DB transaction 안에서 `backend.decisions.require_current_decision(db, actor, case, decision_id)`를 호출한다. 다른 사건이면 DECISION_CASE_MISMATCH, 사건 버전이 다르면 VERSION_CONFLICT, 이후 사건 변경/새 판단이 있으면 STALE_SUPPORT_DECISION으로 차단한다. snapshot GET은 외부 API 호출용 확인 경로이며, 조회 후 별도 작업 사이의 경쟁 상태는 transaction 안의 helper로 재확인해야 한다.

현재 구현은 **A 보고서가 사용할 실제 사람 결정과 검증 인터페이스**까지다. A 보고서 생성기·내보내기·기관 제출은 아직 연결하지 않았다. 보고서 파일 생성과 기관 제출을 같은 상태로 표시하면 안 된다.

## 검증과 남은 범위

서버 전체 88개·프론트 13개 테스트와 기본 build 통과. Render 시연 모드 브라우저 5개에서 판단 기록·revision·사건 변경 표시·보고서 stale 차단·교사 화면 분리와 기존 데모 로그인/깨우기를 확인했다. 이전 배포 단계의 기존 업무 브라우저 6개 결과도 보존되어 있으며 이번 판단 흐름은 추가 시연 테스트로 검증했다.

반복 사건 후보/연결·분리, 이전 답변/미응답/미이행·새 증거 비교, 학교별 반복 기준, 원문/공문 버전 관리, 비교 AI는 다음 B-03 작업이다. 동의 녹취/STT·활동 대시보드도 계속 남아 있다. 실제 Render/Vercel 배포·OpenAI 호출·10 MiB 프록시 업로드는 아직 검증하지 않았다.
