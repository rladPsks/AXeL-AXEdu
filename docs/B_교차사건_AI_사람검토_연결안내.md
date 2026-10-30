# B 교차 사건 AI·사람의 비교 검토 연결

2026-10-31, 통합 계약 v1.6. Render 무료 + Vercel 시연 구성을 유지하고 같은 DB/AI 실행기를 사용한다. 실제 모델 호출·A 보고서 생성기 연결·클라우드 배포 완료를 뜻하지 않는다.

## 1. 사용자 흐름과 책임

관리자가 **반복·새 사실**에서 두 사건을 대조한 뒤 다음 순서로 진행한다.

1. 비교할 원문 버전·업무·지원 기록을 명시적으로 선택한다. 두 사건의 기본 정보와 선택한 출처만 포함한다.
2. **선택한 자료로 비교 준비**로 불변 입력 묶음을 만든다. 두 사건의 버전·출처별 당시 내용·학교 검토 기준을 함께 보존한다.
3. 필요하면 **AI 사건 비교 시작**으로 제안을 생성한다. 모델이 없더라도 사람이 직접 대조해 기록할 수 있다.
4. AI 제안은 별도로 검토한다. 검토 완료(SUCCEEDED)가 사람의 최종 비교 기록이나 학교 지원 결정은 아니다.
5. 사람이 검토 사유·관찰 구분·확인 수준·실제 출처를 선택해 **사람의 비교 검토 저장**을 수행한다. AI 관찰을 불러와도 사유 입력과 별도 저장이 필요하다.
6. **지원 판단**에서 현재 유효한 비교 검토를 출처로 참조할 수 있다. A 보고서는 기존 지원 판단 helper를 통해 최신 여부를 확인한다.

이 흐름은 사건 연결/분리·실제 답변 발송·업무 배정·총괄 변경·외부 기관 제출·종결을 수행하지 않는다. 신고 표현과 감정·횟수만으로 부당 민원을 단정하거나 외부 이관하지 않는다.

## 2. 비교 입력 API

관리자 인증과 같은 학교의 두 사건 접근 권한을 요구한다.

| API | 내용 |
|---|---|
| POST /api/cases/{case_id}/comparison-inputs | 두 사건의 버전을 확인하고 선택한 출처의 내용을 고정 |
| GET /api/cases/{case_id}/comparison-inputs | 저장 입력, 당시 두 사건 버전, 출처, 기준, 현재 stale 여부 |
| POST /api/cases/{case_id}/comparison-reviews | 사람이 검토한 비교 관찰을 revision으로 기록 |
| GET /api/cases/{case_id}/comparison-reviews | 검토 이력과 현재 stale 여부 |
| GET /api/comparison-reviews/{review_id} | 특정 불변 검토 기록과 현재 상태 |

입력 예시:

```json
{
  "expected_version": 3,
  "related_case_id": "previous-case",
  "expected_related_version": 2,
  "source_refs": [
    {"case_id":"current-case","resource_type":"CASE","resource_id":"current-case","version":3},
    {"case_id":"previous-case","resource_type":"CASE","resource_id":"previous-case","version":2},
    {"case_id":"current-case","resource_type":"DOCUMENT_VERSION","resource_id":"saved-version-id","version":2}
  ]
}
```

출처는 두 사건에서 각각 하나 이상, 총2~20개다. 원문 버전 외 CASE/TASK/SUPPORT_REQUEST/FILE도 API에서 명시 선택할 수 있다. UI는 두 사건 기본 정보 외 최대18개의 원문/업무/지원 기록을 선택한다. 각 출처는 지정한 사건에 실제로 속해야 하고 중복을 금지한다. 파일 권한·음성 제외·원문 revision은 기존 snapshot 규칙을 따른다. 전체 입력 상한은 1 MiB다.

입력 준비는 생성용 인프라 기록이므로 사건 버전을 올리지 않는다. 입력은 요청자·시각과 함께 불변 테이블에 보존하며 동일 Idempotency-Key 재시도는 같은 ID를 돌려준다.

## 3. AI 실행과 결과

기존 agent-runs 경로에서 purpose=COMPARE_CASES를 사용한다. input_refs는 COMPARISON_INPUT 하나만 허용한다. resource_id는 준비한 입력 ID, version은 불변 입력 버전 1이다. 이 타입을 다른 생성 목적에 직접 넣는 요청은 거부한다.

```json
{
  "expected_version":3,
  "purpose":"COMPARE_CASES",
  "input_refs":[{"resource_type":"COMPARISON_INPUT","resource_id":"saved-input-id","version":1}]
}
```

서버 `OPENAI_API_KEY`/`OPENAI_MODEL`이 준비되면 공식 Responses SDK의 Pydantic 구조화 출력을 사용한다. `store=False`, 외부 도구 없음, 기존 timeout/lease/재시도/취소/복구를 유지한다. 키/모델이 없으면 기능이 준비되지 않은 상태를 표시하며 가짜 모델 결과로 대체하지 않는다. 사양 참고: [공식 Structured Outputs 안내](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

결과는 summary, findings, missing_information, follow_up_questions다. findings의 category는 NEW_FACT/NEW_EVIDENCE/UNANSWERED_FOLLOWUP/UNFULFILLED_ACTION/REPEATED_CONTENT/REPORTING_LANGUAGE/NEEDS_CONFIRMATION이고 assessment는 FACT/CLAIM/UNVERIFIED다. NEW_FACT는 새롭게 기록된 사실 관련 내용을 구분하는 표식이며 주장을 사실로 자동 인증하지 않는다.

각 관찰의 source_ids는 묶음 안에 실제로 저장한 **원래 출처 ID**를 인용한다. 입력 묶음 ID를 원문 출처인 것처럼 인용할 수 없다. 없는 출처·비어 있는 인용·중복 인용은 adapter와 worker에서 거부한다. 입력 내용 안의 명령/링크는 데이터로 취급하며 규정·기관·기한을 새로 만들지 않도록 지시한다. 부족한 자료나 한쪽 자료만으로 판단할 수 없는 내용은 미확인으로 남긴다. 거절/불완전 응답은 성공 처리하지 않는다.

어느 사건 버전이나 학교의 반복 검토 기준이 달라지면 입력과 AI 결과는 stale이다. 새 실행·제안 수락·사람 검토에 사용하려면 현재 자료로 새 입력을 만든다. 비교 입력의 stale은 accept_stale=true로 우회할 수 없다. 생성 중 바뀐 자료의 결과는 과거 제안으로 조회할 수 있어도 현재 판단에 적용할 수 없다. 권한 변경은 API 조회·worker 전후·결과 목록에서도 재확인한다.

## 4. 사람의 검토와 지원 판단·보고서

사람 기록은 expected_version, input_id, reason, findings, 선택 reviewed_run_id/supersedes_id를 받는다. 관찰 내용과 실제 출처는 필수다. AI를 참조하면 같은 입력으로 생성한 COMPARE_CASES 실행이 현재 버전에서 검토 완료되어 있어야 한다.

같은 현재 사건/비교 사건 조합별로 revision을 올리고 최신 ID를 supersedes_id로 확인한다. 이 사람 검토는 **현재 사건을 기준으로 한 방향성 있는 기록**이다. 기존의 순서 없는 사건 연결/분리 이력과 구분한다. 저장 시 현재 사건 버전을 1 올리고 감사와 함께 원자적으로 저장한다. 이전 검토는 덮어쓰지 않으며 감사 실패 시 모두 취소한다. 교사에게 보여주는 공통 이력에는 이 관리자 전용 이벤트를 노출하지 않는다.

InputRef에 COMPARISON_REVIEW를 추가했다. resource_id는 사람 검토 ID, version은 검토 revision이다. 현재 유효한 사람 검토만 새 지원 판단이나 REVIEW_SUPPORT의 출처로 선택할 수 있다. 지원 판단에는 당시 두 사건 자료·사람의 관찰·참고 AI 결과가 보존된다.

검토를 저장하면서 생긴 현재 사건의 버전 변경은 새 사람 기록을 즉시 무효화하지 않는다. 지원 판단이 그 기록을 소비해 자기 사건 버전을 올리는 경우에도 지원 판단의 recorded_case_version을 기준으로 유효성을 확인한다. 이후 다른 사건 변경·학교 기준 변경·새 검토로의 대체는 별도 의존성으로 추적한다. AI를 통해 간접 참조한 비교 자료도 같은 검사를 적용한다. **현재 사건 버전이 그대로여도 비교 사건이 바뀌면 A의 지원 판단 snapshot API/helper에서 보고서 사용을 차단한다.**

지원 판단을 보고서로 사용할 때는 기존 `backend.decisions.require_current_decision`을 같은 transaction에서 호출한다. 자료 준비/조회와 실제 사용 사이의 경쟁 상태를 화면 표시만으로 판단하지 않는다. A 보고서 생성기 자체와 기관 제출은 아직 연결하지 않았다.

## 5. 충돌·재조회와 검증

같은 비교 사건의 최신 자료를 다시 불러올 때 이전 폼을 유지하며 출처가 오래되면 저장을 잠근다. 다른 비교 사건으로 이동할 때 미저장 검토가 있으면 확인한다. 새 입력을 명시적으로 준비하거나 선택하기 전까지 선택된 묶음이 다른 사람의 새 묶음으로 자동 교체되지 않는다. 충돌 후에도 입력한 사유와 관찰 내용을 보존한다.

서버 전체107개·프론트13개·시연 브라우저8개·기존 업무 브라우저6개 테스트를 검증했다. 실제 SDK의 mock transport는 structured Responses 요청·모델 ID·store=false·원래 출처 인용과 거절 처리를 확인하며 네트워크를 사용하지 않는다. 브라우저의 AI 비교는 테스트 도구가 등록한 RULE handler로 검증하며 화면에 실제 모델 호출이 아님을 표시한다. 제품 Registry에는 이 가짜 결과를 등록하지 않는다.

브라우저 재현 시 `python tools/e2e_demo_server.py 새임시폴더 --comparison-fixture --comparison-ai-fixture`를 사용한다. 두 옵션은 검증 도구 전용이고 제품 자동 시드나 실제 DB에 추가 기능을 켜지 않는다. 프론트는 VITE_SCHOOL_AGENT_DEMO=1, 5174 포트로 실행한 뒤 playwright.demo.config.ts를 사용한다.

실제 OpenAI 응답 품질·Render/Vercel 배포·10 MiB 프록시 업로드는 아직 확인하지 않았다. 다음은 동의 녹취/STT·활동 대시보드와 A 실제 모듈 통합이다. 실모델 검증과 외부 통합을 완료하지 않은 상태에서 전체 제품 완료로 표시하지 않는다.
