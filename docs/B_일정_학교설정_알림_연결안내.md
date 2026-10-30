# B 일정·학교 설정·앱 알림 연결 안내

검증: 서버 69개·프론트 10개·실제 서버 브라우저 6개 테스트와 production build 통과. 권한 변경은 새 가상 계정 DB에서만 검증했으며 실제 계정은 변경하지 않았다. 브라우저 검증에는 학교 설정·부재 대체·일정·앱 확인·인계 거절·권한 변경 후 기존 토큰 폐기·업무 재배정을 포함한다. 실제 OpenAI 호출과 A 모듈 통합은 아직 검증하지 않았다.

확정 계약 v1.3의 추가 계약이다. 기존 업무 생성/회신 본문과 사건 OPEN/CLOSED 상태는 유지한다. 이번 추가는 일정·수행자 변경·학교 설정·부재 대체·앱 수신함·인계 거절/취소다.

## 1. 실행과 채널

기존 실행 방식대로 API와 React를 실행하면 된다. API lifespan에서 앱 수신함 worker가 2초 간격으로 동작한다. 이 worker는 OpenAI 실행기와 분리되어 있어 모델 호출을 기다리지 않는다.

- 채널은 **앱 수신함**이다. 이메일·문자·외부 메신저를 전송하지 않는다.
- QUEUED는 저장된 전달 대기, DELIVERED는 대상자의 앱 수신함에 게시됨, ACKNOWLEDGED는 대상자가 알림 확인을 눌렀음, FAILED는 전달 실패다.
- 알림 확인은 실제 업무 확인/회신이나 지원 요청의 수신 확인을 대신하지 않는다. 지원 수신 확인은 기존 support-requests API로 따로 저장한다.
- SQLite outbox와 원 업무 변경을 같은 transaction으로 저장한다. 감사 실패 시 알림 생성도 취소된다.
- API 재시작 후 QUEUED 알림을 재처리한다. 여러 worker가 동시에 실행되어도 DB transaction·중복 키로 전달 중복을 막는다.
- 수신자는 현재 활성 구성원이고 사건 접근 권한이 있어야 한다. 실패 재시도는 한 주기 최대 3회이며, 관리자의 명시적 재시도는 이력을 유지하면서 3회분을 추가한다.
- 긴급 알림을 일반 알림 backlog보다 먼저 처리한다.
- 별도 점검은 `python -m backend.notifications --once`로 할 수 있다. API와 같은 SCHOOL_AGENT_DB를 사용한다. API 내 worker를 끄는 테스트는 `create_app(..., inbox_worker=False)`다.

업그레이드 이전 사건의 최초 알림을 일괄 소급 생성하지 않는다. 미확인 지원·기한 경과 업무는 현재 정책에 따라 별도 알림을 만든다. 긴급 도움도 DELIVERED만으로 실제 사람의 지원이 확보되었다고 표시하지 않는다.

## 2. 일정과 수행자

| 경로 | 본문 | 권한 |
|---|---|---|
| PUT /api/tasks/{task_id}/schedule | expected_version, planned_start_at 또는 null, due_at 또는 null, reason | 지정 수행자 또는 ADMIN |
| POST /api/tasks/{task_id}/reassign | expected_version, assignee_id, reason | ADMIN |

공통 Bearer·Idempotency-Key가 필요하다. 성공 시 사건 version +1·감사 1건이며 총괄자는 바꾸지 않는다.

- 일정은 timezone이 있는 ISO 8601만 받는다. 서버는 UTC로 정규화하고 화면 입력은 한국시간으로 명시한다.
- 시작/기한을 모두 지정하면 시작 ≤ 기한이어야 한다. PUT은 두 일정 값의 전체 교체이며 null로 해제할 수 있다.
- 기한은 학교가 정한 업무 일정이다. 법정 처리 기한으로 간주하지 않는다.
- 완료 업무의 일정 변경/재배정과 종결 사건의 변경은 차단한다.
- 재배정은 같은 학교의 활성 구성원으로만 가능하다. 새 수행자는 사건 참여자로 추가하고 REQUESTED부터 다시 확인한다.
- 기존 회신은 감사 이력에 보존하며 현재 reply는 초기화한다. 이전 수행자는 이후 회신을 대신 저장할 수 없다.
- 이전 수행자의 사건 참여 권한은 자동 삭제하지 않는다. 계정/사건 열람 정책과 업무 수행 권한을 구분한다.
- GET /api/cases/{case_id}의 tasks에 schedule 객체를 추가했다. planned_start_at/due_at/updated_by/updated_at/reason을 포함하며 없으면 null이다. GET /api/my/tasks에도 due_at을 추가했다.

화면에서는 업무 카드의 ‘업무 일정 조정’, ‘업무 수행자 변경’을 사용한다. 원문 회신·일정 조정 사유·지원 결과는 허용된 사건 이력에서 다시 볼 수 있다.

## 3. 학교 설정 버전

학교 설정은 사건 버전과 독립적이다. 변경 본문의 필드는 **expected_settings_version**이다. 모든 변경에 Idempotency-Key를 적용하며 version 불일치는 409 SETTINGS_VERSION_CONFLICT다. 학교 설정 성공은 settings_version을 반환하고 사건 version을 올리지 않는다.

| 경로 | 범위 |
|---|---|
| GET /api/school/settings | ADMIN의 현재 설정·부재·업무분장 조회 |
| PUT /api/school/settings | 당번 관리자·지원 미확인 기준·기한 알림 유예·일반 알림 |
| GET /api/school/members | ADMIN의 같은 학교 구성원 ID/role/active 조회 |
| GET /api/school/settings/timeline | ADMIN의 최근 100개 설정 감사 이력 |
| POST /api/school/absences | ADMIN의 부재 기간·대체자 등록 |
| POST /api/school/absences/{id}/cancel | ADMIN의 부재 설정 해제, reason 필수 |
| POST /api/school/responsibilities | ADMIN의 업무 이름·담당자·대체자 등록 |
| POST /api/school/responsibilities/{id}/remove | ADMIN의 업무분장 해제, reason 필수 |
| GET /api/school/contacts | 교직원의 활성 업무분장·지원 연결 관리자 조회. 부재 사유/권한 변경 이력 제외 |

설정 초기 version은 1이다. 초기 개발 기본값은 duty_admin_id=null, support_ack_minutes=60, overdue_grace_minutes=0, alerts_enabled=true다. 분 기준은 1~10080 또는 유예 0~10080의 운영 설정이며 제도상 의무 시간이 아니다.

PUT /school/settings는 전체 교체다. 누락된 필드는 기본값으로 바뀌므로 A는 기존 값을 포함해 보낸다. duty_admin_id는 같은 학교의 활성 ADMIN 또는 null이다. 부재 등록의 user_id/substitute_id는 같은 학교·같은 역할의 활성 구성원이며 자신을 대체자로 지정할 수 없다. 겹치는 활성 부재 기간은 차단하고 끝 시각부터는 부재가 끝난 것으로 판단한다. 취소·재등록으로 변경하며 원래 이력은 삭제하지 않는다.

업무분장의 substitute_id는 표시용 역할 분담이다. 실제 지원 요청의 부재 대체는 현재 유효한 staff_absences와 당번 관리자 정책을 사용한다. 여러 업무의 대체자를 임의로 추측해 전역 배정하지 않는다.

## 4. 지원 대체와 미확인 알림

지원 요청의 기존 coordinator_id 입력은 유지한다. 서버는 다음 순서로 지원 담당을 연결한다.

1. 요청한 활성 ADMIN이 부재 중이 아니면 그대로 연결.
2. 부재 중이면 해당 기간의 대체자를 확인. 대체자가 또 부재 중이면 연쇄 확인하되 순환은 차단.
3. 가능한 대체자가 없으면 설정된 당번 ADMIN을 확인.
4. 아무도 가능하지 않으면 요청을 잃지 않도록 원래 담당에게 남기고 NO_AVAILABLE_SUBSTITUTE를 표시.

응답·support_requests에 실제 coordinator_id, 최초 requested_coordinator_id, routing_reason, assigned_at을 구분한다. 단순 대체 연결은 총괄 이전이 아니다. 지정된 실제 지원 담당만 ACKNOWLEDGED/IN_PROGRESS/COMPLETED를 저장한다.

생성 이후 부재가 시작된 REQUESTED 요청도 다음 worker 처리 주기에 대체자를 확인하며, 미확인 시간 기준을 기다리지 않는다. 가능한 대체자가 없으면 요청자/총괄에 대체 확인 필요 알림을 남긴다.

assigned_at부터 support_ack_minutes가 지나도 REQUESTED이면 담당/총괄에 미확인 알림을 만든다. 가능한 다른 당번/대체자가 있으면 지원 담당만 다시 연결하고 SUPPORT_REROUTED 감사와 사건 version +1을 저장한다. 재배정 시 assigned_at을 갱신해 새 담당의 확인 시간을 보장한다. 이미 확인한 요청은 이 경로에서 재배정하지 않는다.

일반 알림을 끈 경우에도 URGENT 요청/지원 처리/미확인 알림은 유지한다. 일반 알림 설정이 법적 긴급성 판단이나 실제 지원 완료를 뜻하지 않는다.

## 5. 수신함 API

| 경로 | 본문/권한 |
|---|---|
| GET /api/notifications | 현재 사용자 수신함. 미확인 우선 최대 100개, 현재 사건 접근 권한 재검사 |
| POST /api/notifications/{id}/acknowledge | 본인 알림, 본문 {} + Idempotency-Key |
| GET /api/school/notification-status | ADMIN의 최근 100개 저장/전달/확인/실패 상태 |
| POST /api/notifications/{id}/retry | 같은 학교 ADMIN의 실패 알림 재시도, 본문 {} + Idempotency-Key |

확인/재시도는 전달 메타데이터 변경이므로 사건 버전과 expected_version은 사용하지 않는다. 알림에는 민원 원문·학교 지원 사유·파일명·음성을 담지 않고 종류·사건/자원 ID만 저장한다. 관련 사건을 열 때 권한을 다시 확인하며 오래된 사건 cache를 갱신한다. 미확인 알림을 먼저 표시하므로 새 확인 이력 때문에 오래된 미확인 항목이 숨겨지지 않는다. 100개 이상의 미확인은 화면에 100+로 표시한다.

## 6. 인계 거절·취소

- POST /api/handovers/{id}/decline: 지정 인수 ADMIN만. expected_version/reason 필수.
- POST /api/handovers/{id}/cancel: 현재 총괄이자 요청자만. expected_version/reason 필수.
- PENDING → ACCEPTED/DECLINED/CANCELLED로 확장했다. 처리자·시각·사유를 보존한다.
- 거절·취소는 기존 총괄을 유지한다. 새 인계 요청을 만들 수 있다. 종결 검사에서는 PENDING만 미완료 인계로 센다.
- 기존 PENDING/ACCEPTED 값은 유지하며 적용 migration에서 기존 행과 ID를 보존한다. A는 추가 enum을 화면 mapper에 반영해야 한다.

## 7. 사용자가 승인한 구성원 권한 관리

사용자는 [구성원 권한 설정 승인 범위](구성원_권한설정_승인범위.md)의 제한을 적용한 기능 개발을 명시적으로 승인했다. 실제 사용자 계정의 역할을 즉시 변경하라는 승인은 아니며 이번 검증은 새 가상 DB에서만 수행했다.

`PUT /api/school/members/{user_id}`는 같은 학교의 기존 구성원을 대상으로 expected_settings_version, role(ADMIN/TEACHER), active, reason을 받는다.

- 호출자는 같은 학교의 유효한 ADMIN이어야 한다. 자신의 권한 변경은 차단한다.
- 사건 총괄·미완료 업무/지원·대기 인계·당번·현재/예정 부재·업무분장에 영향을 주는 강등/비활성화는 먼저 인계/해제하도록 차단한다.
- 현재는 종결 사건 총괄도 보호한다. 필요한 경우 재개 후 정상 인계를 거쳐 정리해야 하며 이 API가 과거 총괄을 임의로 바꾸지 않는다.
- 같은 학교·역할 조건과 책임 확인을 하나의 쓰기 transaction 안에서 처리해 새 배정과 충돌하지 않게 한다.
- 변경 대상의 세션을 폐기한다. 재활성화해도 이전 토큰은 복구하지 않는다. 다음 연결에는 새 정상 인증 세션이 필요하다. 실제 기관 로그인은 아직 후속 범위다.
- 학교 감사 이력과 세션 폐기를 같은 transaction으로 저장한다. 감사 실패 시 역할/활성 상태와 기존 세션을 모두 되돌린다.

기존 ADMIN/TEACHER 외 기관 직책별 세부 권한이나 신규 본인 확인 계정 생성 기능은 추가하지 않았다.

## 8. A 연결 지점과 다음 범위

- A는 원래 업무 생성/회신 본문을 바꾸지 않아도 된다. 일정·재배정·부재·학교 권한은 새 경로로 호출한다.
- 신규 도메인 API도 B의 mutate를 적용하고 필요 알림을 같은 transaction에서 enqueue한다. 학교 설정은 school_command와 별도 설정 버전을 사용한다.
- 학교 설정/멤버/연락망/수신함 cache는 학교·사용자 scope로 구분한다. 권한 변경 대상의 세션은 다시 연결하므로 이전 cache를 재사용하지 않는다.
- 실제 원문 접수·A의 의무 기반 종결 guard는 여전히 A 모듈 연결이 필요하다. B의 교사 회신·지원 결과·일정 사유 이력은 열람 권한 안에서 확인할 수 있다.
- 다음 B 작업은 반복·새 증거·미응답 비교, 사람의 지원 결정 snapshot과 A 보고서 연결, 동의 녹취/STT, 활동 집계/대시보드다. 실제 OpenAI 호출 검증은 로컬 키·모델 설정 후 수행한다.
