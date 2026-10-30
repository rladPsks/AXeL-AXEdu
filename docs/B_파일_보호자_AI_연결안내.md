# B 파일·보호자 관계·OpenAI 실행기 연결 안내

작성일: 2026-10-30. 이전 [공통 기반 연결 안내](B_공통기반_연결안내.md)에 이어지는 구현 기록이다. OpenAI는 사용자가 선택한 공급자다.

## 현재 구현과 검증

- 비공개 파일: 크기 제한·형식 signature/텍스트 검사·업로드·목록·권한 검사 후 다운로드·다운로드 이력·화면.
- 보호자: 교직원과 분리된 개발 세션, 학교 관리자의 관계 확인/해제, 관계 검사 함수·관리 화면.
- AI: 실행 원장·시작/조회/검토/취소·멱등 재확인·worker lease/heartbeat·재시도/중단 복구·결과 fence·화면.
- OpenAI: 공식 Python SDK 3.41.0의 Responses API·Pydantic 구조화 응답, 지원 검토 handler, 서버 환경변수, `store=False`.
- 검증: 서버 49개, 공통 API client 7개, 실제 서버 브라우저 3개, 프론트 build, pip check 통과.
- **아직 검증되지 않은 것:** 실제 OpenAI 계정의 모델 호출·응답 품질·과금/가용성. 현재 실행 환경에 OPENAI_API_KEY와 OPENAI_MODEL이 없다. SDK 요청은 가상 HTTP transport로 검증했다. 테스트 handler의 RULE 결과를 실제 모델 결과로 표시하지 않는다.

참고한 공식 문서: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), [Responses Python reference](https://developers.openai.com/api/reference/python/resources/responses).

## 1. 파일 API

`GET /api/file-policy`는 인증 후 `{max_bytes, extensions}`를 반환한다. 기본 상한은 개발용 10 MiB이며 `SCHOOL_AGENT_MAX_FILE_BYTES`로 설정한다. 기관 운영 정책이나 STT 공급자의 확정 상한은 아니다.

```http
POST /api/cases/{case_id}/files?filename=note.txt&expected_version=3&category=EVIDENCE&visibility=CASE
Authorization: Bearer <교직원 세션>
Idempotency-Key: <같은 파일 요청의 재시도에는 같은 키>
Content-Type: application/octet-stream

<파일 바이트 자체>
```

- multipart나 JSON/base64가 아닌 **binary body**다. 메타데이터는 query로 전달한다. 기존 JSON API의 expected_version 본문 규칙에 대한 명시적 예외다.
- category: EVIDENCE/SOURCE/AUDIO/EXPORT. visibility: CASE/RESTRICTED.
- 지원 확장자: txt/md/pdf/png/jpg/jpeg/wav/mp3/ogg. UTF-8 텍스트와 형식 signature를 검사한다. 전체 decoder 검증·악성 파일 검사는 아직 없다.
- 201 응답: `case_id, version, file_id, filename, size_bytes, sha256, media_type, visibility`. 업로드는 사건 도메인 변경으로 version +1·감사 1건이다.
- 멱등 hash에는 실제 바이트의 SHA-256과 메타데이터가 포함된다. 같은 키·같은 path/query·같은 파일은 최초 응답을 반환한다. 같은 key/path에 다른 파일을 보내면 409다. query는 저장된 route 문자열에 포함되지 않지만 정규화 메타데이터는 body hash로 비교한다.
- request stream을 제한 크기까지 읽는다. 비인가 요청은 바이트를 읽기 전에 검사하며 저장 직전에 다시 검사한다. 초과는 413, 빈 파일/형식/이름 오류는 422다.
- 이 개발 구현은 파일 content를 private_files BLOB에 저장한다. 파일·메타데이터·감사·멱등 응답을 한 SQLite transaction으로 commit/rollback하므로 파일시스템 orphan이 발생하지 않는다. 향후 대용량 저장소 adapter로 바꾸더라도 file_id API를 유지한다.
- `GET /api/cases/{case_id}/files`: 허용된 메타데이터 배열. 경로와 content는 반환하지 않는다. 현재 파일은 불변이며 input_ref의 파일 version은 1이다.
- `GET /api/files/{file_id}/download`: Bearer 인증·학교/사건·파일별 권한 검사 후 attachment로 응답한다. nosniff·no-store와 다운로드 이력을 적용한다.
- CASE는 사건 접근자에게, RESTRICTED는 등록자와 같은 학교 ADMIN에게만 보인다. 등록자도 사건 권한이 해제되면 접근할 수 없다. 보호자 토큰으로는 이 API를 사용할 수 없다.
- 음성 업로드는 동의나 STT 분석을 의미하지 않는다. 현재 일반 AI snapshot에서 AUDIO 파일 참조를 차단한다. 녹취 동의·전사는 후속 모듈이다.

프론트는 공통 ApiClient.upload(path, file, key), download(path)를 사용한다. 다운로드 링크에 토큰을 넣거나 비공개 URL을 공개 정적 경로로 만들지 않는다.

## 2. 보호자 관계 경계

기존 memberships의 ADMIN/TEACHER를 변경하지 않았다. 보호자는 guardian_accounts/guardian_sessions로 별도 관리하며 교직원 token과 호환되지 않는다.

| API | 역할/내용 |
|---|---|
| GET /api/guardian/session | 보호자 세션 확인, guardian_id/school_id/active만 반환 |
| GET /api/guardian/cases/{case_id}/access | 본인 사건 관계 검사, case_id/relationship_verified만 반환 |
| GET /api/cases/{case_id}/guardian-links | 같은 학교 ADMIN의 관계 확인 이력 조회 |
| POST /api/cases/{case_id}/guardian-links | ADMIN이 expected_version/guardian_id/verification_note로 관계 확인 |
| POST /api/guardian-links/{link_id}/revoke | ADMIN이 expected_version/reason으로 연결 해제 |

- 관계 확인과 해제는 사건 version·감사·멱등 처리를 적용한다. 해제는 종결 사건에서도 가능하다.
- 학교가 다른 보호자, 없는 관계, 해제된 관계는 대외 접근에서 모두 404다. 만료/비활성 계정은 401이다.
- `backend.guardians.authenticate_guardian(db, request)`와 `guardian_case(db, actor, case_id)`를 A의 대외 API에서 호출한다. guardian_case의 반환 row는 서버 내부 전용이다. A는 **허용 필드만 새 DTO에 담아 반환**하며 dict(row)를 외부에 그대로 반환하지 않는다.
- 교직원 사건·이력·파일 API는 보호자에게 열리지 않는다. 대외 답변·진행 DTO는 A의 기능으로 아직 미연결이다.
- guardian 계정은 신뢰할 수 있는 본인 확인 adapter 또는 개발 fixture에서만 생성한다. 보호자가 스스로 guardian_id를 제출해 세션/관계를 만드는 공개 API는 없다.
- seed는 guardian/other-guardian/foreign-guardian의 **가상** guardian_tokens도 별도 출력한다. 최초 사건 관계는 자동 연결하지 않는다. 실제 기관 본인 확인은 아직 구현하지 않았다.

## 3. OpenAI 설정과 실행

서버·worker에서 다음을 동일하게 설정한다. 키는 채팅·Git·브라우저에 넣지 않는다. `.env` 자동 로더는 없으므로 아래는 PowerShell 환경변수 방식이다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
$localApiKey = Read-Host 'OpenAI API 키' -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $localApiKey).Password
$env:OPENAI_MODEL = Read-Host '계정에서 사용할 구조화 응답 지원 모델 ID'
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

다른 터미널에서도 같은 OPENAI_API_KEY/OPENAI_MODEL과 SCHOOL_AGENT_DB를 설정한 뒤:

```powershell
.\.venv\Scripts\python.exe -m backend.worker
```

worker는 별도 프로세스다. API 서버만 실행하면 요청은 QUEUED에 남는다. 한 작업만 처리하는 점검 명령은 `python -m backend.worker --once`다. 환경변수를 바꾸면 API와 worker 모두 다시 시작한다.

모델 ID는 특정 모델로 고정하지 않았다. 계정에서 사용할 수 있는 구조화 응답 지원 모델을 설정한다. 두 변수 중 하나라도 없으면 기본 REVIEW_SUPPORT handler를 등록하지 않고 시작 API에서 503 AGENT_UNAVAILABLE을 반환한다. 화면의 생성 버튼도 비활성화한다.

현재 REVIEW_SUPPORT는 사건 기본 정보·선택한 업무/지원 기록·명시적으로 선택한 텍스트 파일을 검토하는 **제안**이다. 화면은 사건과 최근 업무 10건/지원 9건까지 참조하며 첨부는 자동 전송하지 않는다. RAG 근거 검색·반복 사건 비교·사람의 최종 지원 판단·보고서는 별도 후속 기능이다.

실제 모델 호출 점검은 키 설정 후 `python tools/openai_smoke.py`로 할 수 있다. 이 명령은 가상 사건만 사용하는 새 임시 DB에서 실제 요청 한 번과 사람 검토 경로를 실행한다. 현재 개발 검증에서는 키가 없어 이 명령의 실제 모델 성공을 확인하지 않았다.

## 4. AI 실행 API와 상태

| API | 요청/응답 |
|---|---|
| GET /api/agent-capabilities | 등록된 purpose/generation_mode/version 배열 |
| POST /api/cases/{case_id}/agent-runs | expected_version/purpose/input_refs/retry_of_run_id?, 202 |
| GET /api/cases/{case_id}/agent-runs | 본인 또는 ADMIN이 볼 수 있는 실행 배열 |
| GET /api/agent-runs/{run_id} | 상태·단계·입력 버전·결과·오류·stale·시도 횟수 |
| POST /api/agent-runs/{run_id}/review | expected_version/decision(ACCEPT 또는 REJECT)/reason/accept_stale? |
| POST /api/agent-runs/{run_id}/cancel | expected_version/reason |

모든 POST는 Idempotency-Key가 필요하다. 생성·진행·검토·취소는 실행 원장의 변화이며 **사건 version을 올리지 않는다.** 생성물의 사건 적용은 별도의 권한 있는 도메인 명령에서 감사·version +1을 수행한다.

input_refs는 `[{resource_type,resource_id,version}]` 형식이며 1~20개다. 현재 CASE/TASK/SUPPORT_REQUEST/FILE을 지원한다. FILE은 불변 version 1, 나머지는 현재 사건 version이다. 같은 사건의 저장된 자료와 접근 권한만 허용한다. 파일 text/plain은 최대 10,000자와 잘림 여부를 snapshot에 담고, PDF/이미지는 이 일반 handler에서 원문 추출 없이 메타데이터만 참조한다.

QUEUED → RUNNING → WAITING_REVIEW → SUCCEEDED가 기본이다. SUCCEEDED는 생성물 검토 완료이며 응답 승인·담당 배정·기관 제출·종결이 아니다. 기계적 handler는 requires_review=False로 생성 성공까지 기록할 수 있으나 도메인을 자동 변경하지 않는다.

- 실패는 FAILED, 취소/검토 거절은 CANCELLED. transient 실패는 제한 횟수 내에서 QUEUED/retry_wait로 돌아간다.
- 입력 사건이 변경되면 stale=true다. 최신 버전과 대조한 reason·accept_stale를 제출해야 수락할 수 있다. 검토 후 다시 사건이 변경된 경우에도 재검토할 수 있다.
- 각 실행은 요청자 또는 같은 학교 ADMIN만 읽는다. 입력 파일의 권한도 읽기/worker 실행 직전/결과 저장 직전에 재검사한다.
- `require_usable_result(db, actor, case, run_id, purpose)`를 A/B의 도메인 mutate 내부에서 호출한다. 같은 사건·목적·검토 완료·최신 검토 버전이 아니면 적용하지 않는다.
- snapshot·handler/prompt 버전·공급자/모델·실행 이력을 저장한다. API키와 예외 원문은 저장하지 않는다. 사람 검토/취소 사유는 실행 이력에 남긴다.
- SDK 응답은 Pydantic schema로 검증하며 입력에 없는 source_id가 있으면 결과를 거절한다. 출처 ID 검증이 내용의 진실성이나 법적 정확성을 보장하지는 않으므로 사람의 원문 대조가 필요하다.

## 5. A handler 등록과 worker 복구

`backend.agents.Handler`는 purpose, execute(snapshot), result_model, version, generation_mode, requires_review, max_attempts, metadata를 가진다. execute는 결과만 반환하고 사건 DB·외부 제출을 직접 변경하지 않는다.

A가 자기 registry factory에서 B의 `create_registry()`를 호출한 뒤 분류/답변/번역/보고서 handler를 register한다. `SCHOOL_AGENT_REGISTRY_FACTORY=패키지.모듈:함수`를 **API와 worker 모두 동일하게** 설정한다. 이것은 신뢰할 수 있는 로컬 개발 코드의 진입점이며 HTTP 요청에서 임의 module 경로를 받지 않는다.

worker는 DB transaction으로 한 작업을 점유하고, 외부 호출 중에는 DB 쓰기 transaction을 열어 두지 않는다. heartbeat로 lease를 연장한다. 중단되어 lease가 만료되면 제한 횟수 안에서 재점유한다. max_attempts는 기본 3, handler별 최대 5다. 오래된 worker의 token으로는 새 점유/취소 뒤 결과를 덮을 수 없다. API와 worker의 handler/prompt/model 설정이 다르면 HANDLER_CHANGED로 실패한다.

외부 요청 자체는 프로세스 중단 시 중복 호출될 수 있다. 이 worker가 보장하는 것은 하나의 유효 결과만 저장하는 것이며 외부 공급자의 정확히 한 번 과금/실행을 보장하지 않는다. 실행 취소도 이미 시작한 외부 요청의 비용을 소급 취소하지 않는다.

## 6. 다음 범위

일정/원문 연결·알림/대체자·인계 거절/취소·반복 비교·사람의 지원 결정 snapshot·A 보고서 연결·동의 녹취/STT·활동 집계·전체 통합은 계속 개발한다. 실제 운영 인증·파일 보유기간·기관 제출도 이 구현으로 완료된 것이 아니다.
