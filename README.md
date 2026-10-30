# AXeL-AXEdu

Vercel 프론트 + Render 무료 API/내부 worker + 임시 SQLite 시연 배포는 [배포 안내](docs/배포_안내.md)를 따릅니다. 자동 시드·계정 버튼은 서버 `SCHOOL_AGENT_AUTO_SEED=1`/`SCHOOL_AGENT_DEMO=1`, 프론트 `VITE_SCHOOL_AGENT_DEMO=1`에서만 동작합니다. 기본 로컬 인증은 기존 토큰 방식입니다. Render가 잠들면 시연 데이터는 초기화됩니다.

A·B 통합 시 [확정 계약 v1.3](docs/개발자_AB_통합계약_확정_v1.md)을 우선 적용합니다. React 공통 구조·레이아웃·API 클라이언트도 B 담당입니다. B 기준 충돌 방지 규칙과 현재 구현·후속 구현 계약을 구분한 문서입니다.

최신 개발: 일정·업무 재배정·부재 대체·학교 설정·앱 수신함·인계 거절/취소와 승인된 구성원 권한 관리를 추가했습니다. **[일정·학교 설정·알림 연결 안내](docs/B_일정_학교설정_알림_연결안내.md)**를 확인하세요. 비공개 파일·보호자 관계·OpenAI 실행기는 [이전 연결 안내](docs/B_파일_보호자_AI_연결안내.md)에 있습니다. 실제 OpenAI 호출 검증, A 원문/종결 조건 연결, 반복 비교·동의 녹취·대시보드는 남아 있습니다.

공통 실행 구조는 [B 공통 기반 연결 안내](docs/B_공통기반_연결안내.md)를 참고하세요. 아래는 첫 서버 구현 당시의 기록이며, 구현 범위와 추가 API는 위 최신 안내를 우선합니다.

학교 민원 에이전트 개발자 B의 첫 서버 구현입니다. Python 3.12 기준, FastAPI·SQLite를 초기 선택으로 사용합니다. 기술 선택은 팀 합의에 따라 조정할 수 있습니다.

## 실행 (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

시드 명령은 빈 개발 DB에 가상 사건 `demo-case`와 개발 계정을 생성하고 무작위 Bearer 토큰을 출력합니다. 토큰 원문은 DB에 저장하지 않으며 8시간 후 만료됩니다. 기관 인증·로그인 기능은 아직 구현하지 않았습니다. 기본 서버는 시드나 세션을 자동 생성하지 않습니다. 기본 DB는 `data/private/dev.sqlite3`이며 `SCHOOL_AGENT_DB`로 변경합니다. 별도 DB 시드에는 `--db 경로`를 사용합니다.

API 문서: <http://127.0.0.1:8000/docs>. 요청 헤더에 `Authorization: Bearer <시드에서 받은 토큰>`을 넣습니다. 변경 요청에는 `Idempotency-Key`와 본문의 `expected_version`도 필요합니다. API 연결 예시는 [계약 문서](docs/b-first-slice.md)를 참고하세요.

API 계약 재생성: `.\.venv\Scripts\python.exe -m backend.export_contract`. 모든 설치 버전을 재현하려면 `requirements-lock.txt`를 설치합니다. 이 파일은 Python 3.12·Windows에서 검증한 개발 환경의 전체 의존성입니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

학교·사건 권한, 중복 요청, 동시 수정 충돌, 총괄 인수 수락, 지원 수신 확인, 종결 가드, 재시작 후 저장, 감사 실패 시 트랜잭션 취소를 검증합니다.

## 구현 범위

- 세션 검사·학교 소속·사건 참여 기반 접근 검사
- 교사 업무 생성·확인·완료 회신
- 학교 지원 요청·지정 관리자 확인·조치·결과
- 총괄 인계 요청·지정 인수자 수락
- 남은 업무·지원·인계 확인 후 종결, 사유를 남기는 재개
- 서버 UTC 시각·추가형 감사 이력·사건 버전·중복 방지

전체 제품이나 B-01~04의 완료를 뜻하지 않습니다. 현재 React·보호자 관계·AI 실행기·파일·migration·일정·대체자·앱 알림은 구현했습니다. URGENT도 앱 수신함으로 전달하지만 이메일/SMS는 연결하지 않았습니다. 실제 기관 인증·OpenAI 호출 검증·반복 비교·녹취·대시보드는 후속 작업입니다.

A의 접수·분류·근거·답변·번역·보고서 기능은 포함하지 않았습니다. 사건 테이블과 조회는 첫 연결을 위한 최소 계약이며, 현재 종결 검사는 B가 구현한 세 테이블만 확인합니다. A의 답변 전달·승인·후속 업무 조건을 연결하기 전에는 제품 전체의 종결 조건을 충족하지 않습니다. [작업 경계와 다음 순서](docs/b-first-slice.md)를 참고하세요.
