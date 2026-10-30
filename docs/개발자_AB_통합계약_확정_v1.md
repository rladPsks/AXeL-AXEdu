# 개발자 A·B 통합 계약 — 확정 v1.5

확정일: 2026-10-30 (Asia/Seoul)
기준: 개발자 B의 현재 FastAPI·SQLite 코드 및 보관된 PRD·기술 명세·역할분담·유저플로우
적용 저장소: `rladPsks/AXeL-AXEdu` / B 작업 브랜치: `codex/b-foundation`, PR 대상: `yujinb`

v1.1 역할 변경: 사용자의 확정에 따라 **React 공통 구조·레이아웃·API 클라이언트(기존 상대점수 4)는 B가 담당한다.** 라우터·공통 UI·provider·캐시/오류 처리·공통 사건 shell의 구조도 B가 작성한다. A는 그 기반에 자기 기능 화면을 연결한다. 보관된 역할분담 원문보다 이 변경을 우선한다. 이 항목만 이관했으므로 기존 상대점수 합계는 A 36 / B 44가 되며, 실제 소요시간을 뜻하지 않는다.

v1.2 구현 갱신: 비공개 파일·보호자 관계 검사·공통 AI 실행기와 화면을 추가했고, 사용자가 공급자로 OpenAI를 선택했다. 기존 업무 API의 호환성은 유지한다. 새 경로·binary 업로드·별도 보호자 세션·실행 전용 상태 변경의 정확한 계약은 [파일·보호자·OpenAI 연결 안내](B_파일_보호자_AI_연결안내.md)를 이 문서의 일부로 적용한다. 실제 모델 성공은 로컬 키/모델 설정 후 검증해야 한다.

v1.3 구현 갱신: 일정·재배정·부재 대체·학교 설정·앱 알림·인계 거절/취소와 사용자가 승인한 구성원 권한 관리를 추가했다. [일정·학교 설정·알림 연결 안내](B_일정_학교설정_알림_연결안내.md)를 계약 일부로 적용한다. 학교 설정은 expected_settings_version을 사용하며 수신함 확인은 사건 버전을 변경하지 않는다. 기존 업무 API 본문은 유지한다.

## 1. 확정 효력과 적용 범위

v1.5 추가 계약: [반복 후보·원문 버전·사건 대조 안내](B_반복비교_원문버전_연결안내.md)를 적용한다. 관리자용 불변 원문 버전·학교별 검토 기준·같은 학교 후보·두 사건 연결/분리를 추가하고 InputRef에 DOCUMENT_VERSION을 확장했다. 기존 enum 값과 업무 API는 유지한다. 비교 전용 교차 사건 AI는 아직 후속 작업이다.

v1.4 추가 계약: 사람의 지원 판단·출처 snapshot·revision과 A 보고서 참조 검증을 구현했다. [지원 판단·보고서 연결 안내](B_지원판단_보고서_연결안내.md)를 이 계약의 일부로 적용한다. 신규 경로는 관리자용이며 기존 업무 API·총괄 변경·종결 규칙은 유지한다. 시연 배포 기준은 [Render 무료 + Vercel 안내](배포_안내.md)다. 반복 비교 전체와 A 보고서 생성은 아직 완료되지 않았다.

사용자의 지시에 따라 **B의 현재 서버 계약을 기준으로 A가 맞춘다.** 이 문서는 A에게 전달할 통합 기준이며, 기존 `b-first-slice.md`의 ‘초안·미합의’ 부분을 대체한다. A의 실제 작업 코드와 대조한 결과나 A의 동의가 이미 완료되었다는 뜻은 아니다.

- **[구현]**: 현재 소스에서 확인한 동작. A는 그대로 연결한다.
- **[확정·구현 예정]**: 이번에 확정한 후속 인터페이스·규칙. 아직 호출 가능한 기능으로 표시하지 않는다.
- 이 문서 → 현재 API의 요청 모델·코드 → 생성된 OpenAPI → 과거 설계 예시 순으로 해석한다. 문서와 코드가 다르면 임의로 한쪽을 덮지 않고 담당자가 코드·문서·계약을 함께 수정한다. 미구현 규칙을 현재 동작으로 취급하지 않는다.
- v1에서 기존 경로·필드·enum을 삭제하거나 이름을 바꾸지 않는다. 변경이 필요하면 B가 계약 버전을 올리고 양쪽 적용 순서를 기록한다. 공통 UI 작성 책임은 B로 이관하며 A의 기능별 작성 책임은 유지한다.
- 이 문서 작성으로 서버 기능이나 GitHub 브랜치가 변경되지는 않는다.

## 2. 기술·실행·폴더 기준

| 항목 | 확정 내용 | 상태 |
|---|---|---|
| 서버 | Python 3.12, FastAPI, Pydantic v2 | 구현 |
| DB | 개발 환경 SQLite, `backend.db.Database` 사용 | 구현 |
| 서버 진입 | `backend.main:create_app`, factory 방식 | 구현 |
| 기본 DB | `data/private/dev.sqlite3`, 환경변수 `SCHOOL_AGENT_DB` | 구현 |
| 개발 API | `http://127.0.0.1:8000`, 업무 API prefix `/api` | 구현 |
| 프론트 | `frontend/`, React + TypeScript + Vite, React Router, TanStack Query | 구현 |
| 프론트 패키지 | npm, `frontend/package-lock.json` 하나만 사용 | 구현 |
| 프록시 | Vite `/api` → `http://127.0.0.1:8000` | 구현 |
| Python 의존성 | 기존 requirements 파일 유지, 루트에 별도 서버 프로젝트 생성 금지 | 구현/적용 규칙 |
| 운영 배포 | 운영 DB·기관 인증·호스팅은 이 계약에서 확정하지 않음 | 개발 통합 범위 밖 |

루트 `backend/`, `tests/`, `contracts/`, `docs/`는 유지한다. A가 Next.js API·Express·별도 FastAPI 앱 또는 두 번째 DB로 동일 사건을 관리하지 않는다. 브라우저에서 외부 AI를 직접 호출하지 않는다.

## 3. 파일·기능 소유권

‘주 작성자’는 해당 공통 파일을 최종 반영할 사람이다. 두 사람 모두 자기 기능의 UI·API·저장·AI·검증을 담당한다.

| 경로/기능 | 주 작성자 | 상대의 작업 방식 |
|---|---|---|
| `backend/main.py`, `db.py`, `schema.sql`, `models.py`의 공통 부분 | B | A는 필요한 등록·필드·접근 정책을 변경 요청으로 제공 |
| 세션·학교/사건 권한·버전·멱등·감사·파일 저장·AI 실행기 | B | A도 자기 API에 공통 기반 적용 |
| `backend/features/intake/`, `classification/`, `knowledge/`, `responses/`, `translations/`, `reports/` | A | 신규 기능을 이 영역에 모듈로 제공 |
| 교사 업무·지원·인계·종결·반복 비교·녹취·활동 집계 | B | 기존 코드를 덮지 않고 B 모듈을 호출 |
| `frontend/src/app/`, `shared/`, `lib/api/`, 라우터·공통 레이아웃·provider·npm lockfile | B | A는 기능 컴포넌트와 연결 요청을 제공 |
| `frontend/src/features/teacher-tasks/`, `school-support/`, `repeat-review/`, `audio/`, `dashboard/` | B | A는 공개 컴포넌트만 연결 |
| `frontend/src/features/`의 접수·분류·근거·응답·번역·보고서·보호자 | A | B는 공개 API만 사용 |
| `contracts/openapi.json` | B가 생성·반영 | 수작업 편집 금지. A는 API 변경을 모듈과 함께 제공 |
| 마이그레이션 | 기능 담당자 작성, B가 실행 순서·공통 테이블 검토 | 기존 migration 수정 금지 |
| 테스트·프롬프트 | 기능 담당자 | 공통 정책을 우회하는 테스트·프롬프트 금지 |

`backend/features/`는 신규 기능 배치 규칙이다. 공통 변경 처리는 `backend.commands.mutate`, 접근 검사는 `backend.access`로 추출되었다. A는 이 서비스를 재사용하고 `create_app(feature_routers=..., closure_guards=...)` 확장 지점으로 연결한다. React 공통 기반과 B 업무/지원 화면도 구현되었다. 상세 사용법과 남은 범위는 [B 공통 기반 연결 안내](B_공통기반_연결안내.md)를 따른다.

## 4. 충돌 가능 지점과 확정 해결책

A 코드가 제공되지 않은 상태에서 B 코드·명세의 경계 전체를 점검한 목록이다. 실제 Git 충돌 목록은 합칠 커밋을 대조할 때 별도로 확인한다.

| # | 충돌 지점 | 확정 해결책 |
|---|---|---|
| 01 | 서버 중복 생성 | B FastAPI 앱 하나에 기능 router 등록 |
| 02 | 프론트 루트/패키지 매니저 | `frontend/`, npm 단일 lockfile |
| 03 | 공통 진입점 동시 수정 | 서버·프론트 공통 진입점 모두 B가 최종 반영, A는 기능 모듈 제공 |
| 04 | 사건 테이블 재정의 | 기존 `cases` 6개 필드 유지, A 확장은 별도 테이블 |
| 05 | `id`/`case_id` 혼용 | 사건 조회는 `id`, 변경 응답·관계는 `case_id` |
| 06 | 학생·보호자 이름을 ID로 사용 | 서버 발급 불투명 ID, 동명이인 자동 병합 금지 |
| 07 | 전체 PRD 상태로 `cases.status` 대체 | `OPEN/CLOSED` 유지, 처리 단계는 별도 필드 |
| 08 | 배정과 총괄 변경 혼동 | 업무 배정·지원 요청은 owner 유지, 수락 API만 총괄 변경 |
| 09 | 초기 접수 총괄 누락 | 저장 시 같은 학교 활성 ADMIN을 지정, 없으면 접수 성공 처리 금지 |
| 10 | 역할 종류 확장 | 현재 API role은 ADMIN/TEACHER 유지, 세부 직책은 권한과 분리 |
| 11 | 보호자에 내부 사건 DTO 반환 | 관계 검사와 대외 DTO를 별도 구현하기 전 연결 차단 |
| 12 | 클라이언트 학교·행위자 위조 | 세션에서 결정, 요청 본문 값을 신뢰하지 않음 |
| 13 | A/B 별도 사건 버전 | 사건당 `cases.version` 하나 사용 |
| 14 | 자원별 버전과 사건 버전 혼동 | 업무·지원 변경도 최신 사건 버전 제출 |
| 15 | 409 자동 덮어쓰기 | 재조회·입력 비교·사용자 재확인 후 새 명령 |
| 16 | 더블 클릭·타임아웃 중복 | 같은 명령은 같은 키·본문, 새 의도는 새 키 |
| 17 | 실패 요청 키가 예약된 것으로 처리 | 현재 실패 키는 미저장, 성공 응답만 재사용 |
| 18 | 상태·감사·응답 저장 분리 | 한 트랜잭션으로 원자 저장 |
| 19 | 공통 SQL 위치 기반 INSERT 파손 | 현재 열 추가 금지, 후속 마이그레이션 전에 명시 열 INSERT로 전환 |
| 20 | DB 파일 전달·초기화 | DB/토큰/실데이터 Git 제외, migration·가상 seed만 공유 |
| 21 | 생성 이벤트와 업무 이력 중복 | 도메인 명령당 version +1·감사 1건, 실행 진행 로그는 별도 |
| 22 | AI 생성 성공을 승인으로 표시 | 실행·검토·전달·종결을 별도 관리 |
| 23 | 오래된 AI 결과 반영 | 입력 버전과 최신 버전 비교 후 사람 검토 |
| 24 | 공급자 키·모델·프롬프트 충돌 | B 공통 adapter, A/B 목적별 handler, 서버 설정 사용 |
| 25 | 보고서와 지원 결정 중복 작성 | B의 사람 결정 snapshot을 A 보고서가 참조 |
| 26 | 보고서 생성=기관 제출 | 내보내기·제출·수신 별도 상태, 외부 전송 미구현은 미전송 |
| 27 | A 미완료 답변이 있는데 종결 | A closure guard 등록 전 전체 제품 종결 기능 노출 금지 |
| 28 | 원문/정정 덮어쓰기 | 원본 보존, 수정 버전·출처 ID 별도 저장 |
| 29 | 파일 URL·음성·다운로드 | 비공개 저장, 다운로드 때도 권한 검사 |
| 30 | 녹취 동의와 일반 첨부 혼용 | 동의 없는 STT 호출 금지, 업로드=동의 아님 |
| 31 | 캐시·시연 역할 전환 누출 | 학교/사용자별 cache 분리, 세션 전환 시 폐기 |
| 32 | 프론트의 대문자 enum 변환 | 전송은 영문 enum 그대로, 한국어는 화면 label만 |
| 33 | 시각·시간 단위·날짜 경계 | 서버 UTC ISO 8601, 화면 Asia/Seoul, duration은 초 |
| 34 | 긴급 요청=알림 도착 | 저장·앱 전달·사용자 확인을 분리. URGENT도 수신함 queue/재시도 적용, 업무 수신 확인은 별도 |
| 35 | 학교 설정·권한 설정 동시 편집 | A는 자료/공지/일정, B는 분장/대체/권한/알림 |
| 36 | 변경 API 응답에 임의 wrapper 추가 | 기존 평면 JSON 유지, `{data: ...}`로 일괄 변경 금지 |
| 37 | 목록·pagination 응답 재사용 오류 | 현재 timeline은 배열 유지, 신규 목록은 별도 계약 |
| 38 | OpenAPI 수작업 수정·stale 파일 | 앱에서 재생성하고 기존 경로 보존 확인 |
| 39 | CORS·인증 전달 방식 불일치 | 개발은 Vite 프록시 + Bearer, 쿠키 세션 임의 도입 금지 |
| 40 | DB 변경 번호·테스트 fixture 충돌 | 고유 migration 이름, B 순서 관리, 테스트는 별도 임시 DB |
| 41 | Git의 마지막 수정으로 통째 덮기 | 기능별 PR, 충돌 파일은 담당자 계약 기준으로 병합 |
| 42 | 반복 횟수로 자동 이관 | 후보 제안만 허용, 사실/새 증거/미응답과 사람 판단 분리 |
| 43 | 집계 기간·실제 시간 추정 | 같은 사건 원장 기반, 미기록을 0으로 단정하지 않음 |
| 44 | mock을 실제 기능으로 시연 | 미구현 표시, 실제 서버 경로로 통합 검증 후 완료 |

## 5. 현재 사건·인증·데이터 계약 [구현]

### 5.1 인증과 접근

- `Authorization: Bearer <token>` 필수. 토큰은 개발 seed에서 발급하며 8시간 후 만료된다. 로그인·갱신·기관 인증 API는 없다.
- `GET /api/session` → `{"user_id":"admin","school_id":"demo-school","role":"ADMIN","active":1}`. `active`는 현재 0/1 정수다.
- ADMIN: 같은 학교 사건 접근 가능. TEACHER: `case_participants`에 등록된 사건만 접근 가능.
- 세션 누락/만료/비활성: 401. 다른 학교 또는 없는 사건: 404. 같은 학교 비참여 교사: 403.
- 업무 수행자는 같은 학교의 활성 구성원으로 지정할 수 있다. 현재 생성 코드가 TEACHER로만 제한하지 않으므로 프론트가 이를 서버 계약으로 가정하지 않는다.
- 지원 담당자와 인수 총괄자는 같은 학교의 활성 ADMIN이어야 한다.
- 교직원의 접수 담당자·교장·교감 등 세부 직책 권한은 아직 없다. 보호자는 guardian_sessions의 별도 namespace와 사건 관계 검사로 분리했다. 화면 직책만으로 관리자 권한을 부여하지 않는다.

### 5.2 사건 조회

`GET /api/cases/{case_id}`는 아래 평면 구조다. `tasks`, `support_requests`, `handovers`는 없으면 `[]`이며 배열 내부는 현재 해당 테이블 행의 필드다.

```json
{
  "id": "demo-case",
  "school_id": "demo-school",
  "title": "[가상] 상담 지원 사례",
  "owner_id": "admin",
  "status": "OPEN",
  "version": 1,
  "tasks": [],
  "support_requests": [],
  "handovers": []
}
```

기존 `cases` 열은 `id, school_id, title, owner_id, status, version`이다. 현재 ID 발급기는 32자리 소문자 hex지만 **클라이언트는 ID를 파싱하지 않는다.** `demo-case` 등 fixture ID도 허용한다. 요청 식별자는 trim 후 1~128자, Text는 trim 후 1~10,000자다. 필수 문자열의 빈 값은 허용하지 않으며 nullable 필드에는 `null`을 사용한다.

### 5.3 A의 사건 확장 [확정·구현 예정]

- A의 접수·분류·응답 데이터는 기존 `cases`를 대체하지 않고 `case_details`(사건당 1행), `intakes`(사건당 여러 행), A의 기능 테이블로 확장한다. 열 상세는 해당 기능 PR에서 본 계약에 추가한다.
- `case_details.case_id`는 `cases.id`를 참조한다. A가 별도 사건 ID나 총괄·종결·버전을 중복 저장하지 않는다.
- 접수는 기존 사건 원장 생성 + 최초 접수 + 참여자 + 초기 감사 이벤트를 한 트랜잭션으로 저장한다. 최초 버전은 1, 초기 감사 previous/new version은 0/1이다. 생성에는 `expected_version`이 없고 Idempotency-Key는 필요하다.
- 새 사건의 총괄은 권한 있는 서버 정책으로 지정한 활성 ADMIN이다. 지정 불가 시 409 `OWNER_UNAVAILABLE`로 실패하고 접수 완료 번호를 보여주지 않는다. 입력 보관이 필요하면 ‘미접수 임시 저장’임을 명확히 한다.
- 이후 접수 보완·분류 확정·응답 승인 등 사건 도메인 변경은 사건 버전 규칙을 따른다.
- 처리 단계가 필요하면 `case_details.processing_stage`로 추가한다. `cases.status`의 OPEN/CLOSED와 업무·지원·AI·제출 상태를 혼합하지 않는다.
- 기존 사건 조회에는 호환되는 선택 필드만 추가할 수 있다. 보호자용 조회는 별도 DTO·경로로 구현한다.

## 6. 현재 API 목록과 상태 [구현]

공통 변경 헤더: `Authorization`, `Idempotency-Key`. JSON 변경 본문: `expected_version` 정수 ≥1. binary 파일 업로드는 같은 값을 query로 전달한다. 정의되지 않은 추가 JSON 본문 필드는 422다. `{case_id}`, `{task_id}` 등은 반환받은 실제 ID로 치환한다.

| Method / 경로 | 추가 본문 | 성공 | 권한/조건 |
|---|---|---|---|
| `GET /health` | 없음 | 200 `{status:"ok"}` | 인증 불필요 |
| `GET /api/session` | 없음 | 200 세션 객체 | 유효 세션 |
| `GET /api/cases/{case_id}` | 없음 | 200 사건 객체 | 사건 접근자 |
| `GET /api/cases/{case_id}/timeline` | 없음 | 200 이력 배열 | 사건 접근자 |
| `POST /api/cases/{case_id}/tasks` | `type, assignee_id, question, callback_needed?` | 201 | ADMIN |
| `PATCH /api/tasks/{task_id}` | `status, reply?` | 200 | 지정 수행자 |
| `POST /api/cases/{case_id}/support-requests` | `coordinator_id, type, reason` | 201 | 사건 접근자 |
| `PATCH /api/support-requests/{support_id}` | `status, result?` | 200 | 지정 지원 ADMIN |
| `POST /api/cases/{case_id}/handovers` | `to_owner_id, reason` | 201 | 현재 총괄 ADMIN |
| `POST /api/handovers/{handover_id}/accept` | 없음 | 200 | 지정 인수 ADMIN |
| `POST /api/cases/{case_id}/close` | `reason` | 200 | 현재 총괄 ADMIN |
| `POST /api/cases/{case_id}/reopen` | `reason` | 200 | 현재 총괄 ADMIN |

‘추가 본문 없음’인 인계 수락에도 `{"expected_version": n}`이 필요하다. 조회에는 Idempotency-Key가 필요 없다.

| 대상 | enum / 허용 전이 |
|---|---|
| 업무 type | FACT_CHECK, COUNSEL, CALLBACK, FOLLOW_UP |
| callback_needed | REQUIRED, NOT_REQUIRED, UNDECIDED (생략 기본값) |
| 업무 상태 | REQUESTED → ACKNOWLEDGED → COMPLETED 또는 REQUESTED → COMPLETED |
| 지원 type | ATTEND, JOINT_RESPONSE, TAKEOVER, URGENT |
| 지원 상태 | REQUESTED → ACKNOWLEDGED → IN_PROGRESS → COMPLETED; ACKNOWLEDGED → COMPLETED도 허용 |
| 인계 상태 | PENDING → ACCEPTED / DECLINED / CANCELLED; 수락 시만 총괄 변경 |
| 사건 상태 | OPEN → CLOSED → OPEN |

- 업무 완료 시 `reply`, 지원 완료 시 `result` 필수. 같은 상태로 재변경은 허용되지 않으며 같은 성공 명령의 재시도는 멱등 키로 처리한다.
- 업무 생성은 수행자를 사건 참여자로 추가한다. 지정 수행자는 ADMIN일 수도 있으며 회신 시 ADMIN 우회 권한은 없다.
- TAKEOVER 지원 요청도 owner를 바꾸지 않는다. 한 사건의 PENDING 인계는 최대 1개이며 수락 시만 owner 변경·인수자 참여 추가.
- CLOSED에서는 재개 외 도메인 변경이 차단된다. 현재 종결 가드는 미완료 업무·지원·인계를 검사한다. A의 미전달 답변·검토·후속 조건은 아직 검사하지 않는다.
- 모든 변경 성공 응답은 `case_id, version`과 작업 결과 필드를 포함한다. 업무 ID는 `task_id`, 지원 ID는 `support_request_id`, 인계 ID는 `handover_id`다. URL의 `support_id` placeholder와 응답 필드 이름을 혼동하지 않는다.

## 7. 버전·멱등·트랜잭션·오류 [구현 및 적용 규칙]

1. 사건당 version 하나. 성공한 새 도메인 명령마다 +1, 감사 이벤트 1건. 재시도 응답은 version을 다시 올리지 않는다.
2. 조회의 `version`을 변경의 `expected_version`에 넣는다. 자원별 조회 시각이나 프론트 카운터를 버전으로 사용하지 않는다.
3. 키는 trim 후 1~128자. 범위는 사용자 + 학교 + HTTP method/실제 path + key다. 같은 키·같은 정규화 본문은 최초 성공 HTTP status·본문을 재생한다. 현재 본문 hash는 Pydantic 모델 직렬화 기준이다.
4. 같은 키에 다른 본문이면 409 `IDEMPOTENCY_CONFLICT`. 같은 명령의 네트워크 재시도에는 expected_version까지 동일하게 유지한다. 충돌 후 수정된 명령에는 새 키를 쓴다.
5. 재생 전에도 현재 세션·사건 접근 권한을 검사한다. 재생 응답은 과거 성공 시점의 version일 수 있으므로 최신 상태가 필요하면 재조회한다.
6. 성공하지 않은 명령은 멱등 기록을 저장하지 않는다. 도메인 변경·참여자·version·감사·멱등 응답은 같은 트랜잭션으로 commit/rollback한다.
7. 409 VERSION_CONFLICT에서 무조건 덮어쓰거나 버전 숫자만 바꿔 자동 재전송하지 않는다. 입력을 보존하고 최신 상태와 비교한다.

현재 공통 오류 예시:

```json
{
  "code": "VERSION_CONFLICT",
  "message": "최신 사건을 조회한 뒤 다시 시도하세요.",
  "retryable": false,
  "case_id": "demo-case",
  "run_id": null,
  "request_id": "서버 발급 ID",
  "current_version": 4
}
```

기본 필드는 `code, message, retryable, case_id, run_id, request_id`. 오류에 따라 `current_version`, `fields`, `pending`이 추가된다. case_id는 모든 오류에서 채워진다고 가정하지 않는다. 현재 공통 오류의 retryable 기본값은 false다. 프레임워크의 미등록 경로 404·405까지 같은 봉투가 보장되는 것은 아니므로 클라이언트는 JSON 오류 봉투가 없는 응답도 처리한다.

| HTTP | 대표 code | 화면 처리 |
|---|---|---|
| 401 | SESSION_REQUIRED, SESSION_INVALID | 입력 보존, 세션 재설정 안내 |
| 403 | CASE_FORBIDDEN, ROLE_FORBIDDEN, TASK_FORBIDDEN, SUPPORT_FORBIDDEN, OWNER_REQUIRED, HANDOVER_FORBIDDEN | 권한 없음, 자동 재시도 금지 |
| 404 | CASE_NOT_FOUND, RESOURCE_NOT_FOUND | 대상 접근 불가/없음 |
| 409 | VERSION_CONFLICT, IDEMPOTENCY_CONFLICT, CASE_CLOSED, INVALID_TRANSITION, HANDOVER_PENDING, OPEN_WORK_REMAINS | 최신 상태/충돌 내용 확인 |
| 422 | VALIDATION_ERROR, IDEMPOTENCY_KEY_REQUIRED, INVALID_MEMBER, REPLY_REQUIRED, RESULT_REQUIRED, SAME_OWNER | 입력 수정 |
| 500 | INTERNAL_ERROR | request_id 표시, 성공 여부 재조회 |

현재 응답에는 `X-Request-ID`, `Cache-Control: no-store`를 설정한다. 업무 원문·토큰·AI 키를 오류와 로그에 반사하지 않는다.

## 8. DB 확장·감사·종결 통합 [확정·구현 예정]

- migration runner와 schema_migrations 적용 이력 테이블이 구현되었다. 서버 시작 시 checksum을 검증하고 순서대로 원자 적용한다. schema.sql은 이전 schema snapshot이며 변경은 새 migration으로 추가한다.
- migration 파일은 `backend/migrations/YYYYMMDD_HHMMSS_A_설명.sql` 또는 `_B_` 형식. 이름 중복 금지, 적용 순서는 B가 PR에서 확정한다. 이미 적용된 파일을 수정하지 않고 새 파일을 추가한다.
- seed·감사·업무·지원·인계·세션·멱등 저장은 명시 열 INSERT로 전환했다. 기존 테이블 확장이 필요하면 **기존 DB 업그레이드 검증 → 열 변경** 순서를 지킨다. A는 우선 자기 테이블만 추가한다.
- 테스트별 임시 DB 사용. 개발 DB 삭제·재시드로 migration 성공을 대신하지 않는다. seed는 빈 개발 DB 전용이며 서버가 자동 실행하지 않는다.
- timeline은 현재 배열이며 각 이벤트는 `id, case_id, actor_id, action, previous_version, new_version, created_at, payload`를 포함한다. payload는 JSON 객체로 반환한다. 기존 이벤트 UPDATE/DELETE 금지.
- A 신규 감사 action은 INTAKE_CREATED, CLASSIFICATION_CONFIRMED, RESPONSE_DRAFT_SAVED, RESPONSE_APPROVED, RESPONSE_DELIVERED, REPORT_EXPORTED 등 동작별 이름으로 추가하고 결과 ID를 payload에 남긴다. AI 원문·전체 녹취를 감사 payload에 복제하지 않는다.
- 공통 종결 검사 인터페이스 `check_closure(db, actor, case_id) -> list[{code, resource_type, resource_id, message}]`의 registry와 등록 지점은 구현되었다. A는 미완료 승인·전달·후속 의무를 반환하는 guard를 제공하고 B가 등록한다. 모두 같은 DB 트랜잭션에서 검사한다. A의 실제 guard는 아직 미등록이다.
- A guard가 등록·검증되기 전에는 현재 close API를 B 단위 시연으로만 취급한다. 통합 제품에서 전체 완료를 뜻하는 종결 버튼을 활성화하지 않는다.
- 종결 blocker는 사건별 의무를 기준으로 한다. 모든 사건에 답변·보고서·AI 성공을 일괄 필수로 만들지 않는다. 재개는 사유를 남기고 과거 기록을 유지한다.

## 9. AI 실행 공통 계약 [공통 기반 구현·기능별 확장 중]

공통 실행 API·worker·OpenAI Responses adapter·REVIEW_SUPPORT handler는 구현되었다. 실제 모델 호출 검증과 A의 기능별 handler·동의 전사·반복 비교는 남아 있다. API와 worker는 동일한 registry factory를 사용한다. 아래 공통 봉투를 유지하며 추가 경로/검토/취소/복구 규칙은 v1.2 연결 안내를 따른다.

- B: 실행 원장·공급자 adapter·worker·재시도·권한·복구. A: 분류/RAG/응답/톤/번역/보고서 handler. B: 반복 비교/지원 검토/전사/녹취 요약 handler.
- 예약 경로: `POST /api/cases/{case_id}/agent-runs` (202), `GET /api/agent-runs/{run_id}` (200). 실행 재시도는 새 run을 생성하고 `retry_of_run_id`로 연결한다.
- 시작 본문: `expected_version, purpose, input_refs, retry_of_run_id?`. `input_refs`는 저장된 입력 ID·버전을 참조한다. raw 사용자/학교/역할을 권한 근거로 받지 않는다. 목적별 입력·결과 schema는 handler 담당자가 등록한다.
- purpose: CLASSIFY, SEARCH_EVIDENCE, DRAFT_RESPONSE, ADJUST_TONE, TRANSLATE, GENERATE_REPORT, COMPARE_HISTORY, REVIEW_SUPPORT, TRANSCRIBE_AUDIO, SUMMARIZE_AUDIO.
- 공통 조회 봉투:

```json
{
  "run_id": "불투명 ID",
  "case_id": "demo-case",
  "status": "QUEUED",
  "step": "queued",
  "input_case_version": 3,
  "result": null,
  "error": null,
  "generation_mode": "MODEL"
}
```

- status: QUEUED, RUNNING, WAITING_REVIEW, SUCCEEDED, FAILED, CANCELLED. generation_mode: MODEL, RULE, MANUAL. 화면 표시용 mock을 MODEL로 반환하지 않는다.
- WAITING_REVIEW는 검토용 결과가 저장된 상태다. 검토 후 SUCCEEDED도 생성물 검토 완료만 뜻하며 업무 배정·응답 승인·기관 전송·사건 종결의 근거가 되지 않는다. 이 행위들은 별도 권한 명령이다.
- 시작 시 사건 버전을 검사하고 입력 snapshot/run을 저장하되, 실행 진행 상태만으로 사건 version을 올리지 않는다. 결과를 사건 도메인에 적용하는 별도 명령이 최신 version 검사·감사·+1을 수행한다.
- AI 결과가 만들어진 동안 사건이 변경되면 자동 적용하지 않는다. 입력 버전 차이를 표시하고 재생성 또는 사람의 재검토를 요구한다.
- worker 중단 후 RUNNING 방치 방지·중복 실행 점유 방지·재시도 한도는 B가 구현한다. LLM/STT 외부 호출은 긴 SQLite 쓰기 트랜잭션 밖에서 수행한다.
- 실패 시 error는 `code, message, retryable`을 포함하고 원문·키를 노출하지 않는다. UI timeout은 서버 작업 실패 확정이 아니다. 재조회 후 같은 시작 명령은 같은 멱등 키로 확인한다.
- 모델/프롬프트 버전과 근거 source ID를 실행 원장에 저장한다. 실제 공급자·모델 이름은 서버 설정으로 정하고 인터페이스에 고정하지 않는다.

## 10. B 지원 판단 → A 보고서 계약 [확정·구현 예정]

현재 지원 요청(`support_requests`)은 사람의 지원/이관 판단 문서가 아니다. A가 지원 요청 reason만 보고 외부 이관 결정으로 해석하지 않는다.

예약 조회: `GET /api/cases/{case_id}/support-decisions/{decision_id}`. B가 작성·저장하며 A는 수정하지 않고 snapshot으로 참조한다.

| 필드 | 형식/의미 |
|---|---|
| decision_id, case_id | 불투명 문자열 ID |
| case_version | 결정 저장 직후 사건 버전 |
| decided_by, decided_at | 서버 확인 결정자, UTC ISO 8601 |
| decision | INTERNAL_SUPPORT / SPECIALIST_SUPPORT / EXTERNAL_SUPPORT / KEEP_REVIEWING |
| reason | 사람의 판단 사유 |
| statements | `[{id, kind: FACT/CLAIM/UNVERIFIED, text, source_refs:[]}]` |
| previous_actions | `[{id, summary, occurred_at, source_refs:[]}]` |
| evidence_refs | `[{evidence_id, version, document_number: null 또는 문자열}]` |
| requested_support | 구체적인 요청 지원 내용 |
| destination | `{organization_name: null 또는 문자열, route: null 또는 문자열, verified: boolean}` |
| remaining_school_task_ids | 남은 학교 업무 ID 배열 |
| supersedes_decision_id | 이전 결정을 대체하면 해당 ID, 아니면 null |

`source_refs`는 `{resource_type, resource_id, version}` 객체 배열로 통일한다. 확인되지 않은 날짜·공문·기관명은 생성하지 않고 null/UNVERIFIED로 남긴다. 결정 변경은 원본 덮어쓰기 대신 새 decision ID로 저장한다.

A 보고서는 `decision_id`, 해당 snapshot, 생성 시 `case_version`, 필드별 source_refs를 보관한다. 생성 후 결정이 바뀌면 ‘이전 판단 기준’으로 표시하고 다시 검토한다. 보고서 검토 상태는 DRAFT/REVIEWED, 외부 제출 상태는 NOT_SENT/SENT/RECEIVED로 분리한다. 내보내기는 REPORT_EXPORTED 이력만 남기며 NOT_SENT를 바꾸지 않는다. 실제 외부 제출 연동 전에는 SENT/RECEIVED를 자동 설정하지 않는다. 정식 제출·수신 증빙 API는 별도 구현 후에만 사용한다.

## 11. 프론트 연결 계약 [확정·구현 예정]

- B가 제공하는 공통 API 클라이언트만 사용한다. A/B 각 화면에서 fetch·인증·오류·멱등 로직을 다시 만들지 않는다.
- 공통 클라이언트는 JSON 평면 응답, 비JSON 오류 fallback, 401·403·404·409·422·500, 요청 취소와 timeout을 처리한다.
- A/B 기능 공개 진입은 각 `frontend/src/features/<feature>/index.ts`에 둔다. 사건 탭 컴포넌트 기본 props는 `{caseId: string}`. 사용자/학교·query client·API client는 B의 공통 provider에서 가져온다. 화면 role prop을 서버 권한 근거로 삼지 않는다.
- B가 공통 사건 shell·라우터·앱 entry·단일 query client를 작성하고 기능을 연결한다. A는 사건 기본 정보·접수·분류 등 자기 기능 콘텐츠를 제공하며 별도 앱 entry나 두 번째 query client를 만들지 않는다.
- 공통 query key: `['case', schoolId, userId, caseId]`, `['timeline', schoolId, userId, caseId]`. 목록·업무 key도 schoolId/userId를 포함한다.
- 변경 성공 후 해당 사건·timeline·관련 목록/내 업무를 무효화한다. 변경 응답의 version만으로 오래된 상세 데이터를 최신으로 표시하지 않는다.
- 같은 사건의 전송 중 변경 버튼은 중복 제출을 막는다. 다른 화면에서 동시에 수정될 가능성은 서버 version 검사로 처리한다.
- 세션/학교 변경 시 민감한 query cache·폼 임시 데이터·실행 polling을 정리한다. 원문·토큰을 URL이나 영구 localStorage에 저장하지 않는다. 개발 토큰 입력은 메모리 보관을 기본으로 한다.
- AI 생성은 사용자 행동에 따른 mutation이다. 조회 hook·mount effect·자동 새로고침에서 생성 POST를 호출하지 않는다. terminal run 상태에서는 polling 종료.
- 한국어 상태 label은 공통 mapper에서 관리하고 API enum은 그대로 유지한다. 완료·인계·승인·제출은 서버 응답 전에 완료 표시하지 않는다.
- 시각은 서버 UTC ISO 8601로 보관하고 화면은 Asia/Seoul로 표시한다. ‘날짜만’ 값은 YYYY-MM-DD로 구분한다. 활동 소요시간 저장 단위는 초(`duration_seconds`), 표시는 분/시간이다.

## 12. 파일·녹취·보호자·알림 경계 [확정·구현 예정]

- 비공개 파일 메타데이터·저장·다운로드는 B 공통 기반을 사용한다. 파일은 프론트 `public/`에 두지 않는다. A/B는 내부 실제 경로 대신 `file_id`를 공유한다.
- 구현된 다운로드 경로: `GET /api/files/{file_id}/download`. 세션·학교·사건·파일별 권한을 재검사하고 권한 없으면 다운로드하지 않는다. 업로드는 binary body와 query 메타데이터, 저장은 비공개 SQLite BLOB으로 구현했다.
- 업로드 상한·허용 형식은 파일 종류별 서버 정책으로 검증한다. STT 공급자 확정 전 임의 상한을 운영 확정값으로 선언하지 않는다.
- 음성은 B 소유이며 파일 업로드 성공과 동의를 분리한다. 실행 시 동의·권한을 다시 확인한다. 전사 원본·수정 버전·음성 구간 연결을 유지한다.
- 보호자는 내부 GET /api/cases 응답을 받지 않는다. B의 별도 세션·관계 확인/해제·검사 함수는 구현되었으며 실제 본인 확인과 A의 대외 DTO는 남아 있다. 내부 교사 회신·지원 사유·음성·감사 payload를 그대로 노출하지 않는다.
- URGENT는 앱 알림 원장에 저장하고 우선 전달한다. QUEUED/DELIVERED/ACKNOWLEDGED/FAILED를 분리하며 재시도와 부재/미확인 대체를 적용한다. 저장 성공을 사용자 확인으로 표시하지 않는다. 이메일/SMS는 연결하지 않았다. 인계 거절·취소 후 기존 총괄을 유지하며 종결 검사에서는 PENDING 인계만 미완료로 센다.
- 긴급 보호 요청은 일반 AI 분류/생성 완료를 기다리지 않는 독립 동선으로 구현한다.
- 반복 후보와 이관 판단은 분리한다. 반복 수·감정·신고 표현만으로 자동 이관/낙인하지 않는다. 활동 집계는 사건 원장에 근거하며 교사 순위를 만들지 않는다.

## 13. Git 통합·완료 판정

### 고정 통합 순서

1. B가 현재 서버 기반·이 계약·OpenAPI·테스트를 `yujinb`에 커밋·푸시한다. 현재 폴더는 복사본이므로 원격 연결과 브랜치 이력 확인을 먼저 한다. 원격 브랜치를 초기화하거나 강제 푸시하지 않는다.
2. 공통 통합 브랜치는 `codex/integration-v1`로 한다. B 기반 커밋을 출발점으로 만들고 A가 이 기반을 자신의 작업 브랜치에 반영한다. 이 문서가 브랜치를 실제 생성한 것은 아니다.
3. A는 기존 코드 중 UI·기능 코드를 계약 경로로 이식한다. B 서버 진입·원장·상태 enum·인증을 A의 기존 구현으로 통째 덮지 않는다.
4. 공통 서비스 추출·migration runner → A 접수/사건 확장 → A UI/B 업무 연결 → AI → 보고서/반복 → 녹취/집계 순으로 기능별 PR을 통합 브랜치에 합친다.
5. 각 기능 PR이 자기 코드·문서·테스트·필요 migration을 포함한다. 공통 파일 충돌은 위 소유권에 따라 해결한다. 일괄 ours/theirs 선택 금지.
6. 통합 검증 후 저장소의 실제 기본 브랜치로 PR을 만든다. 기본 브랜치 이름을 main/master라고 가정하지 않는다.

### 병합 필수 확인

- 기존 B API 12개 테스트 통과. 기존 테스트를 삭제하거나 권한·version·멱등 검증을 약화해 통과시키지 않는다.
- A 실제 접수 → 사건 ID/version → 업무 요청 → 교사 회신 → 지원 요청 → 관리자 수신/결과 → timeline 재조회가 같은 DB에서 동작.
- 세션 전환·타 학교·비참여 교사 차단, 409 재조회·중복 명령 재생, 재시작 후 저장 확인.
- A guard 등록 후 미완료 답변/후속 의무가 있는 종결 차단. 인계 수락 전 기존 총괄 유지.
- 기능 PR에 DB 변경이 있으면 빈 DB와 이전 개발 스키마 DB 모두에서 업그레이드 검증.
- 프론트 build 성공, 해당 화면 실제 API 연결. OpenAPI 재생성 후 기존 경로·요청 필드 호환 확인.
- AI·다운로드·보호자·녹취 기능은 해당 모듈이 실제 구현된 PR에서 권한·실패 경로 검증. 아직 없는 기능을 통합 완료로 표시하지 않음.

## 14. A에게 전달할 실행 지시

> B의 FastAPI·SQLite 서버와 이 v1.1 계약에 맞춰 주세요. 기존 사건 ID/owner/status/version, Bearer 인증, Idempotency-Key, expected_version, 업무·지원·인계 API는 유지합니다. React 공통 구조·레이아웃·라우터·API 클라이언트·provider는 B가 담당합니다. A는 B의 공통 프론트 기반 위에 접수·분류·근거·답변·번역·보고서 기능을 별도 모듈로 추가합니다. 공통 서버·DB·권한·실행기 변경도 B가 반영합니다. 기존 cases 테이블을 재생성하거나 B 코드를 통째 덮지 말고, 먼저 같은 사건으로 접수→교사 업무→지원 확인 흐름을 연결해 주세요. 문서의 ‘구현 예정’ 경로는 현재 서버에 존재하지 않으므로 실제 API로 연결한 뒤 완료로 표시해 주세요.

## 15. 확인한 근거

- `backend/main.py`: 현재 경로·권한·상태 전이·오류·멱등·종결 검사.
- `backend/models.py`: 요청 필드·enum·길이·추가 필드 거절.
- `backend/schema.sql`, `db.py`, `seed.py`: 현재 원장·트랜잭션·ID·세션·가상 사건.
- `contracts/openapi.json`, `tests/test_workflow.py`, `docs/b-first-slice.md`.
- `docs/references/`의 PRD·기술 구현 명세·2인 역할분담·유저플로우.

v1.0 변경 기록: 사용자 지시로 B 기준 통합 정책 확정. 기존 동작과 미구현 계약을 구분하고 충돌 경계 44개, 소유권, 데이터/API/상태/버전/DB/AI/보고서/UI/Git 규칙을 문서화함.

v1.1 변경 기록: 사용자 확정으로 React 공통 구조·레이아웃·API 클라이언트와 관련 공통 파일 소유권을 A에서 B로 이관. API 동작 변경 없음. 기존 링크 호환을 위해 파일명은 유지함.

v1.2 변경 기록: binary 파일 저장/다운로드·보호자 관계·실행 원장/worker/검토/취소·OpenAI adapter 추가. 실행 전용 명령은 사건 버전을 올리지 않고, 적용 도메인 명령에서만 version+감사 처리. 실제 모델 호출은 키 설정 후 확인. 기존 파일명 유지.
