# B 반복 후보·원문 버전·사건 대조 연결

2026-10-31, 통합 계약 v1.5. Render 무료 + Vercel 시연 설정은 유지한다. 기존 사건/업무/지원/종결 상태와 적용 migration을 수정하지 않고 새 테이블·router·관리자 탭을 추가했다.

이후 [v1.6 교차 사건 AI·사람 검토 안내](B_교차사건_AI_사람검토_연결안내.md)에서 아래의 비교 전용 AI 후속 범위를 구현했다. 최신 구현 여부는 추가 안내를 우선한다.

## 1. 원문·답변 기록

관리자용 **원문·답변** 탭에서 INTAKE(접수 원문), EVIDENCE(추가 증거), OFFICIAL_DOCUMENT(공문/근거), RESPONSE(이전 답변), ACTION(조치)을 기록한다. 제목과 논리 자료 ID는 고정하고 정정할 때 새 revision을 추가한다. 원문 본문·출처/확인 경위·기록 대상 시각·답변 전달 기록·선택한 사건 파일을 버전마다 보존한다. 한국 시간 입력은 UTC로 저장한다.

이는 사람이 입력하거나 A가 연결할 저장 자료다. 내용을 기록했다고 사실 확인·공문 진위 확인·답변 발송이 완료되었다고 표시하지 않는다. PDF/이미지를 자동 파싱하지 않으며 현재는 확인한 텍스트와 기존 비공개 파일 ID를 함께 기록한다. 파일은 같은 사건이어야 하고 AUDIO 첨부는 동의/전사 경로 전까지 거부한다.

| API | 계약 |
|---|---|
| POST /api/cases/{case_id}/documents | expected_version, kind, label, content, provenance, occurred_at, delivery_state, 선택 file_id |
| POST /api/documents/{document_id}/versions | expected_version, expected_document_revision, content, provenance, occurred_at, delivery_state, 선택 file_id |
| GET /api/cases/{case_id}/documents | 모든 원문 버전, 발생/기록 시각 순 |
| GET /api/document-versions/{version_id} | 한 버전과 원래 논리 자료 ID/사건/kind/label |

POST는 Idempotency-Key가 필요하다. 버전 추가 시 사건 버전과 원문 revision을 모두 확인한다. delivery_state는 DELIVERED/NOT_DELIVERED/UNKNOWN/NOT_APPLICABLE이며, 전달/미전달은 RESPONSE에만 허용한다. 실제 메시지를 전송하지 않는다. 기록은 trigger로 수정/삭제를 금지하며 과거 본문과 첨부 연결을 보존한다. 감사 실패 시 새 논리 자료·버전·사건 version·멱등 저장을 모두 되돌린다.

## 2. 학교 기준과 후보

관리자용 **반복·새 사실** 탭에서 학교 내부의 동일인/동일 사안 구분 코드를 기록한다. 주민등록번호나 연락처를 코드로 사용하지 않는다. 입력한 코드의 실제 동일인 여부를 자동 인증하지 않는다.

- PUT /api/cases/{case_id}/comparison-profile: expected_version, 선택 person_key/issue_key(하나 이상), received_at. 본문은 공통 감사의 관리자용 이력에도 남긴다.
- GET /api/school/repeat-settings: configured 여부, 학교 기준, settings_version.
- PUT /api/school/repeat-settings: expected_settings_version, window_days(1~3650), minimum_count(2~1000), 선택 response_delay_hours(1~8760). 학교 설정 공통 버전·멱등·감사를 사용한다.
- GET /api/cases/{case_id}/comparison?after=&limit=: 같은 학교에서 동일인 또는 동일 사안 코드가 일치하는 후보. 기본 limit=30, 최대100, next_cursor 제공.

**기간/횟수 기본 규정은 없다.** 설정 전 configured=false, review_threshold_met=null이며 코드가 같은 이전 사건만 보여준다. 설정 후 현재 사건 접수 시각을 기준으로 기간 내의 이전/동시 접수 사건을 센다. 미래 접수 사건은 현재 사건의 이전 후보에 포함하지 않는다. 여러 원문 버전을 여러 사건으로 세지 않는다. count_including_current는 현재 사건을 포함한 후보 수이며 자동으로 확정한 반복 민원 횟수가 아니다. 기준 도달은 사람이 다시 살펴볼 표시일 뿐 지원 배정·외부 이관을 실행하지 않는다.

## 3. 사건 대조와 연결/분리

GET /api/cases/{case_id}/compare/{related_case_id}는 양쪽 사건의 원문 모든 버전·업무 회신/미완료·학교 지원 결과와 연결 판단 이력을 제공한다. 관리자만 같은 학교의 두 사건을 대조할 수 있다. 다른 사건의 변경을 다시 확인하려면 화면의 **비교 자료 새로고침**을 사용한다.

답변 재확인 표시는 각 논리 자료의 최신 revision만 기준으로 한다. 최신 INTAKE 시각 이후 DELIVERED로 입력한 RESPONSE가 있는지와 학교 response_delay_hours를 대조한다. 이전 전달 기록을 NOT_DELIVERED로 정정하면 과거 버전은 보존하면서 최신 상태로 다시 계산한다. 이것은 저장된 기록 기준의 표시이며 실제 미응답·법정 처리 기한을 확정하지 않는다. 기록이 없다는 이유로 실제 답변이 없었다고 단정하지 않는다.

POST /api/cases/{case_id}/relations:

```json
{
  "expected_version": 1,
  "related_case_id": "other-case",
  "expected_related_version": 1,
  "previous_relation_id": null,
  "state": "LINKED",
  "basis": "SAME_ISSUE",
  "reason": "[가상] 두 접수 원문을 대조한 뒤 관련 사안으로 연결"
}
```

state는 LINKED/SEPARATED, basis는 SAME_PERSON/SAME_ISSUE/BOTH다. 변경할 때 previous_relation_id에 이 사건 쌍의 최신 판단 ID를 넣는다. 양쪽 사건이 OPEN이고 각 expected version이 맞아야 한다. 사건 ID 순서를 정규화하므로 반대 사건에서 보아도 같은 연결 이력을 사용한다. 한 쓰기 transaction 안에서 **양쪽 사건 버전과 감사**를 갱신하고 이력은 덮어쓰지 않는다. 한쪽 감사 실패도 전체를 되돌린다. 같은 키 재시도는 버전을 다시 올리지 않는다.

연결은 총괄 이전이나 참여 권한 공유가 아니다. 교사는 원래 참여하지 않은 비교 사건의 권한을 얻지 않는다. 분리 후 이전 연결 이력은 남는다. 교사에게 보여주는 공통 이력에서는 원문·코드·연결 이벤트를 숨긴다. 새 자료나 연결 판단 변경으로 기존 사람의 지원 판단 snapshot이 오래된 상태가 되면 보고서 참조 검사에서 차단한다. 단, 단순 후보 사건이 변경되었다고 현재 사건의 모든 판단을 자동 무효화하지는 않는다.

## 4. AI/사람의 판단 출처 연결

기존 InputRef에 DOCUMENT_VERSION을 추가했다. resource_id는 논리 자료 ID가 아닌 **불변 버전 행의 ID**, version은 그 자료의 revision이다. 같은 사건의 과거/최신 버전을 함께 선택할 수 있다.

```json
{"resource_type":"DOCUMENT_VERSION","resource_id":"saved-version-id","version":2}
```

공통 snapshot은 본문·출처·시각·전달 기록을 복사하고 API 조회/worker 처리/결과 조회 때 자료 권한을 다시 확인한다. 원문 버전은 관리자 전용이다. 실행 후 요청자가 교사로 바뀌면 원문을 포함한 완료 결과도 목록에서 숨기고 직접 조회를 거부한다. 기존 FILE 입력도 결과 목록에서 현재 파일 권한을 재검사한다.

**AI 지원 검토** 탭에서 관리자가 선택한 원문 버전만 모델 입력에 포함한다. 최대10개 원문을 선택할 수 있고 전체는 사건 포함20개 출처이므로 선택한 원문 수에 따라 최근 업무/지원 기록 일부가 제외될 수 있다. 원문은 자동 포함하지 않는다. 사람의 지원 판단에서도 원문 버전을 출처로 선택할 수 있고 그 당시 내용을 snapshot으로 보존한다.

현재는 같은 사건 안의 원문 여러 버전을 기존 REVIEW_SUPPORT로 검토할 수 있다. **서로 다른 사건의 자료를 묶는 비교 전용 AI handler와 구조화된 차이 판정은 아직 다음 작업**이다. 모델 호출을 이번 검증에서 실제로 실행하지 않았다. A의 접수/RAG·보고서 구현도 별도로 연결해야 한다.

## 5. 검증과 다음 작업

전체 서버 테스트 96개, 프론트 단위 테스트13개, 시연 브라우저6개·기존 업무 브라우저6개, 기본/시연 production build 통과. 검증은 불변 정정 이력·시간대·사건/원문 버전 충돌·출처 권한·학교 기준 기본 미설정·기간/건수·미래 접수 제외·양쪽 사건의 원자적 연결/분리·감사 rollback·전달 정정·권한 변경 후 AI 결과 목록 차단을 포함한다. 시연 브라우저에는 실제 가상 사건 두 개의 원문 정정/후보/연결/분리와 모바일 폭 검증을 추가했다.

브라우저 검증 서버는 `python tools/e2e_demo_server.py 새임시폴더 --comparison-fixture`로 실행한다. 이 옵션은 **검증 도구에만** 두 번째 가상 사건을 추가하며 제품 자동 시드의 기본 사례나 실제 DB를 변경하지 않는다. 기존 시연 브라우저 검증을 재현할 때 이 fixture 옵션을 사용한다.

다음은 교차 사건 비교 AI와 새 사실/미응답/미이행의 검토 기록, A의 실제 보고서 연결, 동의 녹취/STT, 활동 대시보드다. 실제 Render/Vercel 배포·OpenAI 호출·10 MiB 프록시 업로드는 여전히 별도 검증이 필요하다.
