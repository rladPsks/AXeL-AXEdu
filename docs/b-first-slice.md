# 개발자 B 첫 연결 계약 (초안)

> 통합 정책은 [개발자 A·B 통합 계약 — 확정 v1.1](개발자_AB_통합계약_확정_v1.md)으로 대체되었습니다. React 공통 구조·레이아웃·API 클라이언트도 B 담당입니다. 아래 내용은 첫 서버 구현의 연결 예시와 당시 범위 기록입니다.

제공된 PRD·유저플로우·역할분담·기술 구현 명세를 참고해 작성했다. 아래는 이번 구현 계약이며 A와 공동 확정된 계약은 아니다. 최초 저장소에는 README만 있었다.

## 첫 실행 흐름

시드가 생성한 가상 사건을 사용한다. 예시의 토큰은 실제 시드 출력값으로 바꾼다. 프런트엔드는 서버가 반환한 최신 `version`을 다음 변경의 `expected_version`으로 사용한다. 조회 캐시는 학교·사용자별로 구분하고 세션 변경 시 폐기한다.

```http
POST /api/cases/demo-case/tasks
Authorization: Bearer <admin-token>
Idempotency-Key: task-example-1
Content-Type: application/json

{"expected_version":1,"type":"CALLBACK","assignee_id":"teacher","question":"[가상] 보호자 상담 일정을 확인해 주세요.","callback_needed":"REQUIRED"}
```

201 응답은 `case_id`, `version: 2`, `task_id`, `status: REQUESTED`, `owner_id: admin`을 포함한다. 반환된 ID를 이후 요청에 사용한다.

```http
PATCH /api/tasks/<task_id>
Authorization: Bearer <teacher-token>
Idempotency-Key: task-reply-example-1
Content-Type: application/json

{"expected_version":2,"status":"COMPLETED","reply":"[가상] 상담 가능 일정을 확인했습니다."}
```

```http
POST /api/cases/demo-case/support-requests
Authorization: Bearer <teacher-token>
Idempotency-Key: support-example-1
Content-Type: application/json

{"expected_version":3,"coordinator_id":"admin","type":"ATTEND","reason":"[가상] 상담에 함께 참석해 주세요."}
```

```http
PATCH /api/support-requests/<support_request_id>
Authorization: Bearer <admin-token>
Idempotency-Key: support-ack-example-1
Content-Type: application/json

{"expected_version":4,"status":"ACKNOWLEDGED"}
```

`GET /api/cases/demo-case`에서 업무·지원·총괄·버전을 재조회하고, `GET /api/cases/demo-case/timeline`에서 행위자·서버 시각·버전별 사건 이력을 확인한다. 업무 요청·TAKEOVER 유형의 지원 요청도 사건 총괄자를 자동 변경하지 않는다.

## 상태·접근 계약

| 대상 | 허용 전이 | 변경 권한 |
|---|---|---|
| 업무 | REQUESTED → ACKNOWLEDGED → COMPLETED, 또는 바로 완료 회신 | 생성: 학교 관리자, 회신: 지정 수행자 |
| 지원 | REQUESTED → ACKNOWLEDGED → IN_PROGRESS → COMPLETED (확인 후 바로 완료 가능) | 요청: 사건 접근자, 확인/조치: 지정 관리자 |
| 인계 | PENDING → ACCEPTED | 요청: 기존 총괄, 수락: 지정 인수 관리자 |
| 사건 | OPEN → CLOSED → OPEN | 현재 총괄 관리자 |

현재 학교 관리자 전체는 같은 학교 사건에 접근할 수 있다. 교사는 명시적 사건 참여자만 접근하며 업무 배정 시 참여자로 추가된다. 이는 초기 권한 정책이며 역할별 세부 열람 범위·참여 해제 정책·교사 간 상담 기록 분리는 후속 설계 대상이다. 학교가 다르면 404, 같은 학교지만 사건 비참여자면 403, 세션 오류는 401이다. 사용자·학교·역할은 Bearer 세션에서 확인하고 본문에 추가한 임의 필드는 거절한다.

모든 변경은 `Idempotency-Key` 필수다. 사용자·학교·HTTP 경로별 같은 키와 같은 본문은 저장된 응답을 반환한다. 다른 본문이면 409다. 실패 요청은 키를 저장하지 않는다. 이미 성공한 응답 재조회에도 현재 사건 접근 권한이 필요하다. 최신 버전이 다르면 409 `VERSION_CONFLICT`와 `current_version`을 반환한다. 자동 덮어쓰기 대신 재조회·재검토한다.

주요 오류 봉투는 `code, message, retryable, case_id, run_id, request_id`다. 422는 입력 오류, 409는 버전·상태 충돌이다. 각 응답은 `X-Request-ID`와 `Cache-Control: no-store`를 포함한다. 오류는 원문 입력이나 세션 토큰을 반사하지 않는다.

사건·업무 변경, 참여자 추가, 이력, 중복 방지 응답은 같은 SQLite 트랜잭션으로 저장한다. 감사 이벤트의 UPDATE/DELETE는 DB 트리거로 막는다. DB 운영자 수준의 변조 방지를 보장하는 기능은 아니다. 정식 스키마 버전 관리·마이그레이션은 아직 없다. 지금의 `CREATE TABLE IF NOT EXISTS`는 기존 테이블 구조를 업그레이드하지 않는다.

## A와 맞출 경계

- A: React 공통 진입·API 클라이언트·접수·확장 사건 스키마. B: 서버 진입·저장·접근·이력·업무·지원.
- 현재 cases는 시드 기반 최소 모델이다. A의 case/intake 모델을 합의해 별도 마이그레이션으로 확장한다. 현재 OPEN/CLOSED는 전체 PRD 상태 모델을 대체하지 않는다.
- 기본 서버는 프런트엔드 파일이나 CORS를 제공하지 않는다. A의 개발 서버에서 `/api`를 `http://127.0.0.1:8000`으로 프록시하면 같은 출처로 연결할 수 있다.
- `create_app(path)`로 별도 DB를 주입할 수 있다. 도메인 API는 서버의 공통 접근 검사와 `audit` 함수를 적용해야 한다.
- 자동 생성된 OpenAPI는 `contracts/openapi.json`에 저장한다. 세션·중복 방지 헤더는 계약 문서의 요구도 함께 적용한다.
- B의 지원 판단 → A의 보고서 연결 데이터는 아직 구현하지 않았다. 사건/버전·결정자·이유·사실/주장·이전 조치·증거/공문·대상/경로·학교 후속 업무를 다음 계약으로 맞춘다.

## 다음 구현 순서

1. A와 사건/접수·열람 범위·상태/버전 계약 확정, 정식 마이그레이션.
2. AI 실행 봉투·핸들러 등록·상태 조회·실패/재시작 복구, 파일 저장·다운로드 권한.
3. 교사 업무/학교 지원 React 모듈, 원문 접근·일정·알림 전달·대체자·인계 거절.
4. 반복 비교·증거/공문·지연 기준·사람의 지원 판단·보고서 연결.
5. 동의 녹취·STT·구간 정정·요약 검토, 활동 기록과 지원 대시보드.

실제 AI·기관 제출·실시간 알림·녹취 처리는 아직 동작하지 않는다. 가상 데이터와 서버 테스트가 통과한 첫 API 단위로만 평가한다.
