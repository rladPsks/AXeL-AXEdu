# B 공통 기반 연결 안내

첫 공통 기반 단계의 기록이다. 이후 확정 계약 v1.2에서 비공개 파일·보호자 관계·AI 실행기·OpenAI adapter를 추가했다. **현재 기능과 다음 단계 설정은 [파일·보호자·OpenAI 연결 안내](B_파일_보호자_AI_연결안내.md)를 우선 확인한다.** 아래의 ‘아직 없음’과 테스트 수는 첫 단계 당시 범위다.

## 실행

프로젝트 루트에서 Python 3.12 가상환경을 준비한다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

다른 터미널에서:

```powershell
cd frontend
npm ci
npm run dev
```

`http://127.0.0.1:5173`에서 seed가 출력한 admin 토큰으로 연결한다. 업무 수행자로 teacher를 지정한 뒤 연결을 해제하고 teacher 토큰으로 다시 연결해 회신·지원을 요청한다. admin으로 돌아오면 지원 확인·결과를 기록할 수 있다. deputy는 총괄 인수 시연용이다. outsider와 other-admin은 접근 차단 확인용이다.

seed는 빈 개발 DB에만 적용한다. 기존 데이터가 있으면 지우지 말고 별도 DB 경로를 지정한다. seed의 `--db`와 서버의 `SCHOOL_AGENT_DB`를 같은 경로로 설정한다. 실제 기관 로그인은 아직 없고 토큰은 8시간 후 만료된다.

## 서버 확장

- `backend.access`: authenticate, accessible_case, admin, member, participate, fail, DomainError.
- `backend.commands`: mutate, resource_case. resource_case는 현재 tasks/support_requests/handovers만 허용한다. A 신규 자원은 자기 router에서 권한 검사 후 사건 ID를 구하고 mutate 내부에서 사건 접근을 다시 검증한다.
- `create_app(db_path, feature_routers=[router], closure_guards=[check_closure])`로 A router와 종결 검사를 등록한다. 제품 진입 factory에서 등록하고 OpenAPI export도 같은 등록을 사용해야 한다. 예제만 만들고 기본 앱에 등록하지 않으면 실제 서버에 나타나지 않는다.

```python
from fastapi import APIRouter, Request
from backend.models import Command
from backend.commands import mutate
from backend.access import admin

router = APIRouter()

@router.post('/api/cases/{case_id}/example')
def example(case_id: str, body: Command, request: Request):
    def operation(db, actor, case):
        admin(actor)
        # 기능 데이터는 이 db로 저장한다. 여기서 외부 AI를 호출하지 않는다.
        return {'example_id': '실제로 저장한 ID'}
    return mutate(request, case_id, body, 'EXAMPLE_SAVED', operation)
```

종결 guard는 `(db, actor, case_id)`를 받아 `[{code, resource_type, resource_id, message}]`를 반환한다. 남은 의무가 없으면 `[]`. 예외가 나면 종결 변경 전체가 취소된다. 현재 B의 종결 가드에 이 확장 지점은 있지만 A의 답변 가드는 아직 등록되지 않았다. 따라서 전체 종결 버튼은 화면에서 제공하지 않는다.

## DB migration

- 서버 시작의 Database 초기화에서 자동 적용한다. SQL은 `backend/migrations/`에 새 파일로 추가한다.
- `20261030_000000_B_baseline.sql`은 원래 schema의 동결본으로, 새 DB와 기존 B 개발 DB를 모두 수용한다. `backend/schema.sql`은 이전 DB 호환 검증용 snapshot이며 신규 schema 변경의 진입점이 아니다.
- `schema_migrations`에 파일명·내용 hash·적용 시각을 기록한다. 적용된 파일의 수정/삭제와 과거 순서의 새 파일 삽입을 거절한다.
- 적용은 쓰기 transaction 하나에서 수행하며 SQL 실패 시 schema 변경과 적용 이력을 함께 취소한다. 실행 중인 업무 명령과 별도 connection에서 순서를 보장한다.
- migration의 SQL은 transaction 제어문·executescript·PRAGMA foreign_keys 변경을 넣지 않는 순수 schema/data 변경으로 작성한다. COMMIT/ROLLBACK/VACUUM 등은 runner의 원자성을 깨므로 허용하지 않는다.
- A의 사건 확장은 새 테이블로 추가한다. cases의 기존 필드·버전·총괄 의미를 바꾸지 않는다. 명시 열 INSERT를 사용한다.

## 신규 조회 API

| 경로 | 응답 |
|---|---|
| GET /api/cases?limit=50&after= | `{items: CaseSummary[], next_cursor: string 또는 null}` |
| GET /api/my/tasks?limit=50&after= | `{items: TaskWithCaseTitleAndVersion[], next_cursor: string 또는 null}` |
| GET /api/cases/{case_id}/members | `[{user_id, role}]` |

limit는 1~100, after는 이전 페이지의 next_cursor다. 사건/업무 ID 오름차순으로 조회한다. ADMIN은 자기 학교 사건, TEACHER는 참여 사건만 조회한다. 내 업무는 현재 사용자에게 배정된 업무만 반환하고 참여 권한을 다시 확인한다. members는 사건 접근자에게만 제공하며 교사에게는 활성 관리자와 자기 정보만 반환한다. 연락처·세션 hash는 반환하지 않는다.

## 프론트 확장

- B 소유: `src/app/`, `src/shared/`, `src/lib/api/`, styles, Vite·TS 설정, npm lockfile.
- 공통 shell·라우터·API client·session/query provider를 그대로 사용한다. 토큰/원문을 localStorage에 저장하지 않는다.
- A의 기능 모듈은 `src/features/`에 추가하고 `src/app/feature-registry.ts`에 `{id, title, Component}`를 등록하도록 B에게 변경을 제공한다. Component props는 `{caseId: string}`이다.
- 기능 내부에서 `useSession()`의 api, session과 `useScope()`를 사용한다. 새 API client나 query client를 만들지 않는다.
- 사건 조회 key는 `['case', schoolId, userId, caseId]`, 이력은 `['timeline', schoolId, userId, caseId]`다.
- 공통 CommandForm은 version과 멱등 키를 붙이고 불확실한 네트워크 실패 시 같은 key/body로 재확인한다. 409는 재조회 후 사람이 입력을 계속하도록 한다. nullable 선택 입력의 빈 문자열은 null로 보낸다.
- 저장 전 탭/링크/계정 이동과 새로고침에는 입력 소실 확인을 제공한다. 브라우저 뒤로가기의 SPA 전환 차단은 아직 별도 보완 대상이다.
- 현재 화면: 사건 목록·내 업무 목록·업무 생성/확인/회신·지원 요청/확인/결과·인계/수락·이력·재개. 일정·원문 펼침·거절/취소·알림·완전한 종결은 후속 작업이다.

프레임워크 연결 방식은 [Vite 프록시](https://vite.dev/config/server-options), [QueryClientProvider](https://tanstack.com/query/latest/docs/framework/react/reference/functions/QueryClientProvider), [React Router 선언형 구성](https://reactrouter.com/start/declarative/installation)을 참고했다.

## 검증

```powershell
New-Item -ItemType Directory -Path .test-tmp -Force
.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-tmp/check
.\.venv\Scripts\python.exe -m backend.export_contract
cd frontend
npm run build
npm test
```

브라우저 통합 테스트는 개발 DB를 변경하지 않도록 별도 가상 서버를 사용한다. 기존 8000 포트 서버가 있으면 먼저 종료하거나 다른 개발 시간에 실행한다.

```powershell
# 루트 / 첫 터미널. 매 실행마다 새로운 경로 사용, 기존 경로는 덮지 않는다.
.\.venv\Scripts\python.exe tools/e2e_server.py .test-tmp/browser-run-새번호
# 둘째 터미널
cd frontend
npm run dev
# 셋째 터미널: Edge 설치 필요
cd frontend
$env:SCHOOL_E2E_CREDENTIALS = (Resolve-Path ../.test-tmp/browser-run-새번호/credentials.json).Path
npm run test:e2e
```

브라우저 테스트는 격리된 가상 DB를 실제로 변경한다. 재실행은 새 서버/새 DB로 한다. credentials와 test-results는 Git에서 제외한다.

## 구현 상태와 다음 작업

- 확인 완료: 서버 22개 테스트, 공통 API client 5개 테스트, 실제 서버 브라우저 흐름 2개, 프론트 build, 데스크톱/모바일 캡처 점검. 브라우저 검증에는 동시 수정 시 입력 보존, 비참여 계정 격리, 입력 이탈 취소, 저장 후 응답 유실 시 같은 명령 재확인이 포함된다.
- 다음: 비공개 파일·관계 검사·일정/원문 연결 기반, 공통 AI 실행기·복구, 대체자/알림, 반복 비교·지원 결정·보고서 연결, 녹취·대시보드.
- 이 단계는 B 개발 계획 전체 완료가 아니다. RAG/접수 기능은 A의 모듈을 받아 연결해야 한다.
